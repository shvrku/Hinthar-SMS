from datetime import date, datetime, timedelta

from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiResponse
from django.db import transaction
from django.utils import timezone
from django.core.cache import cache
from class_sessions.models import Session, SessionAttendance, CheckIn, AdHocSession, AdHocSessionAttendance
from class_sessions.serializers import (
    SessionSerializer, SessionAttendanceSerializer,
    SessionAttendanceListSerializer, CheckInSerializer,
    AdHocSessionSerializer, AdHocSessionAttendanceSerializer
)
from class_sessions.utils import process_checkin_attendance
from people.permissions import IsAdmin, IsOwnerTeacher, CanCheckIn, IsAuthenticatedNonTerminal, IsTerminalOrAbove
from people.models import Student, User, Teacher, Staff, Subject
from people.views import BulkOperationsMixin
from timetable.models import TimetableSlot, ClassStudent, Class
from timetable.utils import generate_sessions_for_slots, get_month_end


class SessionViewSet(BulkOperationsMixin, ModelViewSet):
    queryset = Session.objects.select_related(
        'teacher__user', 'class_obj',
        'timetable_slot__class_obj', 'timetable_slot__subject',
        'timetable_slot__teacher__user',
    ).order_by('id')
    serializer_class = SessionSerializer
    permission_classes = [IsAuthenticated]
    ordering = ['id']
    
    def get_queryset(self):
        qs = super().get_queryset()
        teacher_id = self.request.query_params.get('teacher_id')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        status_param = self.request.query_params.get('status')
        paid_param = self.request.query_params.get('paid')
        class_obj_id = self.request.query_params.get('class_obj_id')
        
        if teacher_id:
            qs = qs.filter(teacher_id=teacher_id)
        if date_from:
            qs = qs.filter(start_time__date__gte=date_from)
        if date_to:
            qs = qs.filter(start_time__date__lte=date_to)
        if status_param:
            qs = qs.filter(status=status_param)
        if paid_param:
            qs = qs.filter(paid=paid_param.lower() == 'true')
        if class_obj_id:
            qs = qs.filter(class_obj_id=class_obj_id)
        
        return qs
    
    def get_permissions(self):
        if self.action in ['create', 'destroy', 'bulk_delete']:
            return [IsAdmin()]
        return [IsAuthenticated()]

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.paid:
            return Response(
                {'error': 'Cannot delete a session that has already been paid in payroll.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=['delete'])
    def bulk_delete(self, request):
        ids = request.data.get('ids', [])
        if not isinstance(ids, list) or not ids:
            return Response(
                {'error': 'Expected a non-empty list of IDs in {"ids": [...]}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        qs = self.get_queryset().filter(pk__in=ids)
        if qs.filter(paid=True).exists():
            return Response(
                {'error': 'Cannot delete sessions that have already been paid in payroll.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        with transaction.atomic():
            deleted_count, _ = qs.delete()
        return Response(
            {'deleted_count': deleted_count, 'deleted_ids': ids},
            status=status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['patch'], permission_classes=[IsOwnerTeacher])
    def status(self, request, pk=None):
        session = self.get_object()
        new_status = request.data.get('status')
        if not new_status:
            return Response({'error': 'status is required'}, status=400)
        valid_statuses = [c[0] for c in Session.STATUS_CHOICES]
        if new_status not in valid_statuses:
            return Response(
                {'error': f'Invalid status. Must be one of {valid_statuses}'},
                status=400,
            )
        session.status = new_status
        session._audit_user = request.user
        session.save()
        serializer = self.get_serializer(session)
        return Response(serializer.data)


class SessionAttendanceViewSet(BulkOperationsMixin, ModelViewSet):
    queryset = SessionAttendance.objects.select_related(
        'session', 'session__teacher', 'session__class_obj', 'session__timetable_slot',
        'student'
    ).order_by('id')
    serializer_class = SessionAttendanceSerializer
    permission_classes = [IsAuthenticated]
    ordering = ['id']

    def get_queryset(self):
        qs = super().get_queryset()
        session_id = self.request.query_params.get('session_id')
        student_id = self.request.query_params.get('student_id')
        status_param = self.request.query_params.get('status')
        teacher_id = self.request.query_params.get('teacher_id')
        class_obj_id = self.request.query_params.get('class_obj_id')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')

        if session_id:
            qs = qs.filter(session_id=session_id)
        if student_id:
            qs = qs.filter(student_id=student_id)
        if status_param:
            qs = qs.filter(status=status_param)
        if teacher_id:
            qs = qs.filter(session__teacher_id=teacher_id)
        if class_obj_id:
            qs = qs.filter(session__class_obj_id=class_obj_id)
        if date_from:
            qs = qs.filter(session__start_time__date__gte=date_from)
        if date_to:
            qs = qs.filter(session__start_time__date__lte=date_to)

        return qs
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'bulk_create', 'bulk_delete']:
            return [(IsAdmin | IsOwnerTeacher)()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'list':
            return SessionAttendanceListSerializer
        return SessionAttendanceSerializer


class GenerateClassSessionsView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(
        summary="Generate sessions for a class",
        description=(
            "Generate dated sessions from timetable slots for a specific class. "
            "By default generates from today until the end of the current month. "
            "Optionally accepts start_date and end_date to target a different range "
            "(e.g. next month)."
        ),
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'start_date': {'type': 'string', 'format': 'date', 'description': 'Defaults to today'},
                    'end_date': {'type': 'string', 'format': 'date', 'description': 'Defaults to end of month'},
                },
            },
        },
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'class_id': {'type': 'integer'},
                    'date_range': {
                        'type': 'object',
                        'properties': {
                            'from': {'type': 'string', 'format': 'date'},
                            'to': {'type': 'string', 'format': 'date'},
                        },
                    },
                    'total_created': {'type': 'integer'},
                    'total_already_existed': {'type': 'integer'},
                },
            },
        },
    )
    @transaction.atomic
    def post(self, request, class_id):
        try:
            class_obj = Class.objects.get(pk=class_id)
        except Class.DoesNotExist:
            return Response(
                {'error': f'Class with id {class_id} not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        raw_start = request.data.get('start_date')
        raw_end = request.data.get('end_date')
        try:
            start_date = (
                date.fromisoformat(raw_start) if isinstance(raw_start, str) and raw_start
                else raw_start or timezone.localdate()
            )
            end_date = (
                date.fromisoformat(raw_end) if isinstance(raw_end, str) and raw_end
                else raw_end or get_month_end(start_date)
            )
        except ValueError:
            return Response(
                {'error': 'Invalid date format, use ISO 8601 (YYYY-MM-DD)'},
                status=status.HTTP_400_BAD_REQUEST
            )

        slots = TimetableSlot.objects.select_related('teacher', 'class_obj').filter(
            class_obj=class_obj
        )

        created_sessions, existing_sessions = generate_sessions_for_slots(
            slots, start_date=start_date, end_date=end_date
        )

        def _session_summary(session):
            return {
                'id': session.id,
                'timetable_slot_id': session.timetable_slot_id,
                'teacher_id': session.teacher_id,
                'class_obj_id': session.class_obj_id,
                'start_time': session.start_time.strftime('%d/%m/%y %H:%M:%S'),
                'end_time': session.end_time.strftime('%d/%m/%y %H:%M:%S'),
                'status': session.status,
                'paid': session.paid,
            }

        return Response({
            'class_id': class_id,
            'date_range': {
                'from': start_date.isoformat(),
                'to': end_date.isoformat(),
            },
            'total_created': len(created_sessions),
            'total_already_existed': len(existing_sessions),
            'created': [_session_summary(s) for s in created_sessions],
            'already_existed': [_session_summary(s) for s in existing_sessions],
        })


class CheckInViewSet(BulkOperationsMixin, ReadOnlyModelViewSet):
    queryset = CheckIn.objects.select_related('student', 'checked_by').order_by('-timestamp')
    serializer_class = CheckInSerializer
    permission_classes = [IsAuthenticatedNonTerminal]
    ordering = ['-timestamp']

    def get_queryset(self):
        qs = super().get_queryset()
        student_id = self.request.query_params.get('student_id')
        date_param = self.request.query_params.get('date')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        check_in_type = self.request.query_params.get('check_in_type')

        if student_id:
            qs = qs.filter(student_id=student_id)
        if date_param:
            qs = qs.filter(date=date_param)
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)
        if check_in_type:
            qs = qs.filter(check_in_type=check_in_type)

        return qs


class QRCheckInView(APIView):
    permission_classes = [CanCheckIn]
    throttle_scope = 'checkin'

    @extend_schema(
        summary="QR code check-in",
        description="Check in a student using their unique QR check-in token.",
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'check_in_token': {
                        'type': 'string',
                        'description': "The student's unique QR check-in token",
                    },
                },
                'required': ['check_in_token'],
            },
        },
        responses={
            201: CheckInSerializer,
            400: OpenApiResponse(
                response={'type': 'object', 'properties': {'error': {'type': 'string'}}},
                examples=[
                    OpenApiExample(
                        'Missing or invalid token',
                        value={'error': 'check_in_token is required'},
                        response_only=True,
                    ),
                ],
            ),
            409: OpenApiResponse(
                response={'type': 'object', 'properties': {'error': {'type': 'string'}}},
                examples=[
                    OpenApiExample(
                        'Already checked in',
                        value={'error': 'Student already checked in today'},
                        response_only=True,
                    ),
                ],
            ),
        },
    )
    def post(self, request):
        token = request.data.get('check_in_token')
        if not token:
            return Response({'error': 'check_in_token is required'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            try:
                student = Student.objects.select_for_update().get(check_in_token=token)
            except Student.DoesNotExist:
                return Response({'error': 'Invalid check-in token'}, status=status.HTTP_400_BAD_REQUEST)

            today = timezone.localdate()
            if CheckIn.objects.select_for_update().filter(student=student, date=today).exists():
                return Response({'error': 'Student already checked in today'}, status=status.HTTP_409_CONFLICT)

            checkin = CheckIn.objects.create(
                student=student,
                check_in_type='qr',
                checked_by=request.user,
            )
            process_checkin_attendance(checkin)

        serializer = CheckInSerializer(checkin)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class StatsView(APIView):
    permission_classes = [IsTerminalOrAbove]
    STATS_CACHE_KEY = 'stats_counts'
    STATS_CACHE_TTL = 300  # 5 minutes

    @extend_schema(
        summary="System statistics",
        description="Returns record counts for all tables in the system. Terminal, admin, and staff roles only.",
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'users': {'type': 'integer'},
                    'students': {'type': 'integer'},
                    'teachers': {'type': 'integer'},
                    'staff': {'type': 'integer'},
                    'subjects': {'type': 'integer'},
                    'classes': {'type': 'integer'},
                    'class_students': {'type': 'integer'},
                    'timetable_slots': {'type': 'integer'},
                    'sessions': {'type': 'integer'},
                    'session_attendances': {'type': 'integer'},
                    'check_ins': {'type': 'integer'},
                },
            },
        },
    )
    def get(self, request):
        data = cache.get(self.STATS_CACHE_KEY)
        if data is not None:
            return Response(data)

        models = {
            'users': User,
            'students': Student,
            'teachers': Teacher,
            'staff': Staff,
            'subjects': Subject,
            'classes': Class,
            'class_students': ClassStudent,
            'timetable_slots': TimetableSlot,
            'sessions': Session,
            'session_attendances': SessionAttendance,
            'check_ins': CheckIn,
        }
        data = {key: model.objects.count() for key, model in models.items()}
        cache.set(self.STATS_CACHE_KEY, data, self.STATS_CACHE_TTL)
        return Response(data)


class ManualCheckInView(APIView):
    permission_classes = [CanCheckIn]
    throttle_scope = 'checkin'

    @extend_schema(
        summary="Manual check-in",
        description="Check in a student manually using their student ID.",
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'student_id': {
                        'type': 'integer',
                        'description': 'The numeric student ID',
                    },
                },
                'required': ['student_id'],
            },
        },
        responses={
            201: CheckInSerializer,
            400: OpenApiResponse(
                response={'type': 'object', 'properties': {'error': {'type': 'string'}}},
                examples=[
                    OpenApiExample(
                        'Missing or invalid student_id',
                        value={'error': 'student_id must be a valid integer'},
                        response_only=True,
                    ),
                ],
            ),
            404: OpenApiResponse(
                response={'type': 'object', 'properties': {'error': {'type': 'string'}}},
                examples=[
                    OpenApiExample(
                        'Student not found',
                        value={'error': 'Student not found'},
                        response_only=True,
                    ),
                ],
            ),
            409: OpenApiResponse(
                response={'type': 'object', 'properties': {'error': {'type': 'string'}}},
                examples=[
                    OpenApiExample(
                        'Already checked in',
                        value={'error': 'Student already checked in today'},
                        response_only=True,
                    ),
                ],
            ),
        },
    )
    def post(self, request):
        student_id = request.data.get('student_id')
        if not student_id:
            return Response({'error': 'student_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        if not str(student_id).isdigit():
            return Response({'error': 'student_id must be a valid integer'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            try:
                student = Student.objects.select_for_update().get(id=student_id)
            except Student.DoesNotExist:
                return Response({'error': 'Student not found'}, status=status.HTTP_404_NOT_FOUND)

            today = timezone.localdate()
            if CheckIn.objects.select_for_update().filter(student=student, date=today).exists():
                return Response({'error': 'Student already checked in today'}, status=status.HTTP_409_CONFLICT)

            checkin = CheckIn.objects.create(
                student=student,
                check_in_type='manual',
                checked_by=request.user,
            )
            process_checkin_attendance(checkin)

        serializer = CheckInSerializer(checkin)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class AdHocSessionViewSet(BulkOperationsMixin, ModelViewSet):
    queryset = AdHocSession.objects.select_related('teacher__user', 'subject').order_by('id')
    serializer_class = AdHocSessionSerializer
    permission_classes = [IsAuthenticated]
    ordering = ['id']
    
    def get_queryset(self):
        qs = super().get_queryset()
        teacher_id = self.request.query_params.get('teacher_id')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        status_param = self.request.query_params.get('status')
        subject_id = self.request.query_params.get('subject_id')
        
        if teacher_id:
            qs = qs.filter(teacher_id=teacher_id)
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)
        if status_param:
            qs = qs.filter(status=status_param)
        if subject_id:
            qs = qs.filter(subject_id=subject_id)
        
        return qs

    def get_permissions(self):
        if self.action in ['create', 'destroy', 'bulk_delete']:
            return [IsAdmin()]
        return [IsAuthenticated()]

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.paid:
            return Response(
                {'error': 'Cannot delete an ad-hoc session that has already been paid in payroll.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=['delete'])
    def bulk_delete(self, request):
        ids = request.data.get('ids', [])
        if not isinstance(ids, list) or not ids:
            return Response(
                {'error': 'Expected a non-empty list of IDs in {"ids": [...]}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        qs = self.get_queryset().filter(pk__in=ids)
        if qs.filter(paid=True).exists():
            return Response(
                {'error': 'Cannot delete ad-hoc sessions that have already been paid in payroll.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        with transaction.atomic():
            deleted_count, _ = qs.delete()
        return Response(
            {'deleted_count': deleted_count, 'deleted_ids': ids},
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=['patch'], permission_classes=[IsOwnerTeacher])
    def status(self, request, pk=None):
        session = self.get_object()
        new_status = request.data.get('status')
        if not new_status:
            return Response({'error': 'status is required'}, status=400)
        valid_statuses = [c[0] for c in AdHocSession.STATUS_CHOICES]
        if new_status not in valid_statuses:
            return Response(
                {'error': f'Invalid status. Must be one of {valid_statuses}'},
                status=400,
            )
        session.status = new_status
        session._audit_user = request.user
        session.save()
        serializer = self.get_serializer(session)
        return Response(serializer.data)


class AdHocSessionAttendanceViewSet(BulkOperationsMixin, ModelViewSet):
    queryset = AdHocSessionAttendance.objects.select_related(
        'ad_hoc_session__teacher', 'ad_hoc_session__subject', 'student'
    ).order_by('id')
    serializer_class = AdHocSessionAttendanceSerializer
    permission_classes = [IsAuthenticated]
    ordering = ['id']

    def get_queryset(self):
        qs = super().get_queryset()
        ad_hoc_session_id = self.request.query_params.get('ad_hoc_session_id')
        student_id = self.request.query_params.get('student_id')
        status_param = self.request.query_params.get('status')

        if ad_hoc_session_id:
            qs = qs.filter(ad_hoc_session_id=ad_hoc_session_id)
        if student_id:
            qs = qs.filter(student_id=student_id)
        if status_param:
            qs = qs.filter(status=status_param)

        return qs

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'bulk_create', 'bulk_delete']:
            return [(IsAdmin | IsOwnerTeacher)()]
        return [IsAuthenticated()]
