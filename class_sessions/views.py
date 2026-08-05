from datetime import date, datetime, timedelta

from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet, GenericViewSet
from rest_framework import mixins
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiResponse, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.core.cache import cache
from class_sessions.models import Session, SessionAttendance, CheckIn, AdHocSession, AdHocSessionAttendance
from class_sessions.serializers import (
    SessionSerializer, SessionAttendanceSerializer,
    SessionAttendanceListSerializer, CheckInSerializer,
    AdHocSessionSerializer, AdHocSessionAttendanceSerializer
)
from class_sessions.utils import process_checkin_attendance
from people.permissions import IsStaffOrAbove, CanCheckIn
from people.models import Student, User, Teacher, Staff, Subject
from people.views import BulkOperationsMixin
from timetable.models import TimetableSlot, ClassStudent, Class
from timetable.utils import generate_sessions_for_slots, get_month_end


def revert_checkin_auto_attendance(checkin_ids):
    """Revert only roll statuses still attributed to the deleted check-ins."""
    regular_count = SessionAttendance.objects.filter(
        auto_marked_by_checkin_id__in=checkin_ids
    ).update(status='absent', auto_marked_by_checkin=None)
    adhoc_count = AdHocSessionAttendance.objects.filter(
        auto_marked_by_checkin_id__in=checkin_ids
    ).update(status='absent', auto_marked_by_checkin=None)
    return regular_count, adhoc_count


class SessionViewSet(BulkOperationsMixin, ModelViewSet):
    queryset = Session.objects.select_related(
        'teacher__user', 'class_obj',
        'timetable_slot__class_obj', 'timetable_slot__subject',
        'timetable_slot__teacher__user',
    ).prefetch_related('attendances').order_by('id')
    serializer_class = SessionSerializer
    permission_classes = [IsStaffOrAbove]
    ordering = ['id']
    
    def get_queryset(self):
        qs = super().get_queryset()
        teacher_id = self.request.query_params.get('teacher_id')
        class_id = self.request.query_params.get('class_id') or self.request.query_params.get('class_obj_id')
        subject_id = self.request.query_params.get('subject_id')
        date_from = self.request.query_params.get('date_from') or self.request.query_params.get('start_date')
        date_to = self.request.query_params.get('date_to') or self.request.query_params.get('end_date')
        month_param = self.request.query_params.get('month')
        year_param = self.request.query_params.get('year')
        status_param = self.request.query_params.get('status')
        q = (self.request.query_params.get('q') or '').strip()
        
        if teacher_id:
            qs = qs.filter(teacher_id=teacher_id)
        if class_id:
            qs = qs.filter(class_obj_id=class_id)
        if subject_id:
            qs = qs.filter(timetable_slot__subject_id=subject_id)
        if date_from:
            qs = qs.filter(start_time__date__gte=date_from)
        if date_to:
            qs = qs.filter(start_time__date__lte=date_to)
        if month_param:
            qs = qs.filter(start_time__month=month_param)
        if year_param:
            qs = qs.filter(start_time__year=year_param)
        if status_param:
            qs = qs.filter(status=status_param)
        if q:
            qs = qs.filter(
                Q(teacher__name__icontains=q)
                | Q(class_obj__education_level__icontains=q)
                | Q(class_obj__cohort_identifier__icontains=q)
                | Q(status__icontains=q)
            )
        
        return qs

    def destroy(self, request, *args, **kwargs):
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
        with transaction.atomic():
            deleted_count, _ = qs.delete()
        return Response(
            {'deleted_count': deleted_count, 'deleted_ids': ids},
            status=status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['patch'])
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
    permission_classes = [IsStaffOrAbove]
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
        return [IsStaffOrAbove()]

    def get_serializer_class(self):
        if self.action == 'list':
            return SessionAttendanceListSerializer
        return SessionAttendanceSerializer

    def perform_update(self, serializer):
        # A staff edit supersedes any previous campus check-in auto-mark.
        serializer.save(auto_marked_by_checkin=None)

    @action(detail=False, methods=['post'])
    def bulk_upsert(self, request):
        records = request.data.get('records', request.data)
        if not isinstance(records, list):
            return Response({'error': 'Expected a list of attendance records'}, status=status.HTTP_400_BAD_REQUEST)

        valid_statuses = {c[0] for c in SessionAttendance.STATUS_CHOICES}
        
        session_ids = set()
        student_ids = set()
        for r in records:
            s_id = r.get('session_id') or r.get('session')
            st_id = r.get('student_id') or r.get('student')
            if s_id: session_ids.add(int(s_id))
            if st_id: student_ids.add(int(st_id))
            
        existing = {
            (a.session_id, a.student_id): a
            for a in SessionAttendance.objects.filter(session_id__in=session_ids, student_id__in=student_ids)
        }
        
        to_create = []
        to_update = []
        
        with transaction.atomic():
            for r in records:
                s_id = r.get('session_id') or r.get('session')
                st_id = r.get('student_id') or r.get('student')
                if not s_id or not st_id:
                    continue
                s_id = int(s_id)
                st_id = int(st_id)
                status_val = r.get('status', 'present')
                if status_val not in valid_statuses:
                    return Response(
                        {'error': f'Invalid status "{status_val}". Must be one of {sorted(valid_statuses)}'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                
                key = (s_id, st_id)
                if key in existing:
                    obj = existing[key]
                    obj.status = status_val
                    obj.auto_marked_by_checkin = None
                    to_update.append(obj)
                else:
                    obj = SessionAttendance(
                        session_id=s_id,
                        student_id=st_id,
                        status=status_val
                    )
                    to_create.append(obj)
            
            if to_create:
                SessionAttendance.objects.bulk_create(to_create)
            if to_update:
                SessionAttendance.objects.bulk_update(
                    to_update, ['status', 'auto_marked_by_checkin']
                )
                
        return Response({
            'created_count': len(to_create),
            'updated_count': len(to_update)
        }, status=status.HTTP_200_OK)


class GenerateClassSessionsView(APIView):
    permission_classes = [IsStaffOrAbove]

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


class AttendanceMatrixView(APIView):
    permission_classes = [IsStaffOrAbove]

    @extend_schema(
        summary="Aggregated attendance matrix for classes",
        description="Returns combined sessions, students, and attendance records for classes filtered by class, subject, teacher, date range, or month/year.",
        parameters=[
            OpenApiParameter(
                'class_id',
                OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=True,
                description='Integer class cohort ID (required). Values like "all" / "adhoc" are rejected.',
            ),
            OpenApiParameter('subject_id', OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=False, description='Subject ID filter'),
            OpenApiParameter('teacher_id', OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=False, description='Teacher ID filter'),
            OpenApiParameter('date_from', OpenApiTypes.DATE, location=OpenApiParameter.QUERY, required=False, description='Start date (YYYY-MM-DD)'),
            OpenApiParameter('date_to', OpenApiTypes.DATE, location=OpenApiParameter.QUERY, required=False, description='End date (YYYY-MM-DD)'),
            OpenApiParameter('month', OpenApiTypes.INT, location=OpenApiParameter.QUERY, required=False, description='Month number (1-12)'),
            OpenApiParameter('year', OpenApiTypes.INT, location=OpenApiParameter.QUERY, required=False, description='4-digit year'),
        ],
        responses={
            200: OpenApiResponse(description="Success"),
            400: OpenApiResponse(description="Missing or invalid class_id"),
            404: OpenApiResponse(description="Class not found"),
        }
    )
    def get(self, request):
        class_id_raw = request.query_params.get('class_id')
        subject_id_raw = request.query_params.get('subject_id')
        teacher_id_raw = request.query_params.get('teacher_id')
        date_from_raw = request.query_params.get('date_from') or request.query_params.get('start_date')
        date_to_raw = request.query_params.get('date_to') or request.query_params.get('end_date')
        month_raw = request.query_params.get('month')
        year_raw = request.query_params.get('year')

        if not class_id_raw or class_id_raw in ('all', 'adhoc'):
            return Response(
                {'error': 'class_id is required and must be a valid integer class ID'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            class_id_int = int(class_id_raw)
        except ValueError:
            return Response({'error': 'class_id must be a valid integer'}, status=status.HTTP_400_BAD_REQUEST)

        if not Class.objects.filter(pk=class_id_int).exists():
            return Response(
                {'error': f'Class with id {class_id_int} not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        now = timezone.localdate()
        sessions_qs = Session.objects.filter(
            class_obj_id=class_id_int
        ).select_related(
            'timetable_slot__subject', 'teacher__user', 'class_obj'
        ).order_by('start_time')

        if subject_id_raw and subject_id_raw != 'all':
            try:
                sessions_qs = sessions_qs.filter(timetable_slot__subject_id=int(subject_id_raw))
            except ValueError:
                return Response({'error': 'subject_id must be a valid integer'}, status=status.HTTP_400_BAD_REQUEST)

        if teacher_id_raw and teacher_id_raw != 'all':
            try:
                sessions_qs = sessions_qs.filter(teacher_id=int(teacher_id_raw))
            except ValueError:
                return Response({'error': 'teacher_id must be a valid integer'}, status=status.HTTP_400_BAD_REQUEST)

        if date_from_raw:
            sessions_qs = sessions_qs.filter(start_time__date__gte=date_from_raw)
        if date_to_raw:
            sessions_qs = sessions_qs.filter(start_time__date__lte=date_to_raw)

        if not date_from_raw and not date_to_raw:
            try:
                m = int(month_raw) if month_raw else now.month
                y = int(year_raw) if year_raw else now.year
                sessions_qs = sessions_qs.filter(start_time__year=y, start_time__month=m)
            except ValueError:
                pass

        sessions = list(sessions_qs)
        session_ids = [s.id for s in sessions]

        # Enrolled students for this class ONLY
        class_students = ClassStudent.objects.select_related('student').filter(
            class_obj_id=class_id_int
        ).order_by('student__name')
        students = [cs.student for cs in class_students]
        student_ids = [st.id for st in students]

        # Batch query attendance records
        attendances = SessionAttendance.objects.filter(
            session_id__in=session_ids,
            student_id__in=student_ids
        ).values('id', 'session_id', 'student_id', 'status')

        att_map = {(a['student_id'], a['session_id']): a['status'] for a in attendances}

        student_list = []
        for st in students:
            records = {}
            for sid in session_ids:
                records[str(sid)] = att_map.get((st.id, sid), 'absent')
            student_list.append({
                'id': st.id,
                'name': st.name,
                'unique_code': st.unique_code,
                'user_id': getattr(st, 'user_id', None),
                'records': records
            })

        session_list = [
            {
                'id': s.id,
                'start_time': s.start_time.isoformat(),
                'end_time': s.end_time.isoformat(),
                'subject': s.timetable_slot.subject.name if s.timetable_slot and s.timetable_slot.subject else None,
                'subject_id': s.timetable_slot.subject_id if s.timetable_slot else None,
                'teacher_id': s.teacher_id,
                'teacher_name': s.teacher.name if s.teacher else None,
                'class_obj_id': s.class_obj_id,
                'class_name': str(s.class_obj) if s.class_obj else None,
                'status': s.status,
            }
            for s in sessions
        ]

        return Response({
            'class_id': class_id_int,
            'sessions': session_list,
            'students': student_list,
            'attendances': list(attendances),
        }, status=status.HTTP_200_OK)


class AdHocAttendanceMatrixView(APIView):
    permission_classes = [IsStaffOrAbove]

    @extend_schema(
        summary="Aggregated attendance matrix for ad-hoc sessions",
        description="Returns ad-hoc sessions, students, and attendance status map.",
        parameters=[
            OpenApiParameter('subject_id', OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=False, description='Subject ID filter'),
            OpenApiParameter('teacher_id', OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=False, description='Teacher ID filter'),
            OpenApiParameter('date_from', OpenApiTypes.DATE, location=OpenApiParameter.QUERY, required=False, description='Start date (YYYY-MM-DD)'),
            OpenApiParameter('date_to', OpenApiTypes.DATE, location=OpenApiParameter.QUERY, required=False, description='End date (YYYY-MM-DD)'),
            OpenApiParameter('month', OpenApiTypes.INT, location=OpenApiParameter.QUERY, required=False, description='Month number (1-12)'),
            OpenApiParameter('year', OpenApiTypes.INT, location=OpenApiParameter.QUERY, required=False, description='4-digit year'),
        ],
        responses={
            200: OpenApiResponse(description="Success"),
            400: OpenApiResponse(description="Bad Request"),
        }
    )
    def get(self, request):
        subject_id_raw = request.query_params.get('subject_id')
        teacher_id_raw = request.query_params.get('teacher_id')
        date_from_raw = request.query_params.get('date_from') or request.query_params.get('start_date')
        date_to_raw = request.query_params.get('date_to') or request.query_params.get('end_date')
        month_raw = request.query_params.get('month')
        year_raw = request.query_params.get('year')

        now = timezone.localdate()
        sessions_qs = AdHocSession.objects.select_related('subject', 'teacher__user').order_by('date', 'start_time')

        if subject_id_raw and subject_id_raw != 'all':
            try:
                sessions_qs = sessions_qs.filter(subject_id=int(subject_id_raw))
            except ValueError:
                pass

        if teacher_id_raw and teacher_id_raw != 'all':
            try:
                sessions_qs = sessions_qs.filter(teacher_id=int(teacher_id_raw))
            except ValueError:
                pass

        if date_from_raw:
            sessions_qs = sessions_qs.filter(date__gte=date_from_raw)
        if date_to_raw:
            sessions_qs = sessions_qs.filter(date__lte=date_to_raw)

        if not date_from_raw and not date_to_raw:
            try:
                m = int(month_raw) if month_raw else now.month
                y = int(year_raw) if year_raw else now.year
                sessions_qs = sessions_qs.filter(date__year=y, date__month=m)
            except ValueError:
                pass

        sessions = list(sessions_qs)
        session_ids = [s.id for s in sessions]

        # Batch query attendance records
        attendances = AdHocSessionAttendance.objects.filter(
            ad_hoc_session_id__in=session_ids
        ).values('id', 'ad_hoc_session_id', 'student_id', 'status')

        student_ids_in_att = set(a['student_id'] for a in attendances)
        if student_ids_in_att:
            students = list(Student.objects.filter(pk__in=student_ids_in_att).order_by('name'))
        else:
            students = []

        session_list = [
            {
                'id': s.id,
                'date': s.date.isoformat(),
                'start_time': str(s.start_time),
                'end_time': str(s.end_time),
                'subject': s.subject.name if s.subject else None,
                'subject_id': s.subject_id,
                'teacher_id': s.teacher_id,
                'teacher_name': s.teacher.name if s.teacher else None,
                'status': s.status,
            }
            for s in sessions
        ]

        student_list = [
            {
                'id': st.id,
                'name': st.name,
                'unique_code': st.unique_code,
                'user_id': st.user_id,
            }
            for st in students
        ]

        return Response({
            'sessions': session_list,
            'students': student_list,
            'attendances': list(attendances),
        }, status=status.HTTP_200_OK)


class CheckInViewSet(
    BulkOperationsMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    GenericViewSet,
):
    """
    List / retrieve campus check-ins. Staff may DELETE a record to undo a
    mis-tap; the student can then check in again via terminal/QR/manual.
    Lesson attendance rows still attributed to the deleted check-in are safely
    reverted to absent. Any later manual roll edit clears that attribution and
    is therefore preserved.
    """
    queryset = CheckIn.objects.select_related('student', 'checked_by').order_by('-timestamp')
    serializer_class = CheckInSerializer
    permission_classes = [IsStaffOrAbove]
    ordering = ['-timestamp']

    def get_queryset(self):
        qs = super().get_queryset()
        student_id = self.request.query_params.get('student_id')
        date_param = self.request.query_params.get('date')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        check_in_type = self.request.query_params.get('check_in_type')
        q = (self.request.query_params.get('q') or '').strip()

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
        if q:
            qs = qs.filter(
                Q(student__name__icontains=q) | Q(student__unique_code__icontains=q)
            )

        return qs

    @extend_schema(
        summary="Delete a campus check-in",
        description=(
            "Removes a check-in record so staff can correct a mis-tap. "
            "Attendance statuses still auto-attributed to this check-in are "
            "reverted to absent; later manual roll edits are preserved."
        ),
        responses={204: OpenApiResponse(description="Deleted"), 404: OpenApiResponse(description="Not found")},
    )
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        with transaction.atomic():
            revert_checkin_auto_attendance([instance.id])
            instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['delete'])
    def bulk_delete(self, request):
        ids = request.data.get('ids', [])
        if not isinstance(ids, list) or not ids:
            return Response(
                {'error': 'Expected a non-empty list of IDs in {"ids": [...]}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        qs = self.get_queryset().filter(pk__in=ids)
        actual_ids = list(qs.values_list('id', flat=True))
        with transaction.atomic():
            regular_count, adhoc_count = revert_checkin_auto_attendance(actual_ids)
            deleted_count = qs.count()
            qs.delete()
        return Response({
            'deleted_count': deleted_count,
            'deleted_ids': actual_ids,
            'reverted_session_attendances': regular_count,
            'reverted_adhoc_attendances': adhoc_count,
        })


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


class CheckInLookupView(APIView):
    """
    Resolve a single student for the check-in terminal WITHOUT creating a check-in.

    Accepts one of:
      - check_in_token  (from a scanned QR code)
      - unique_code     (e.g. "HIS26-00001", typed manually)

    Returns only safe display fields (never the QR token, never the full roster)
    so staff can confirm the correct student before committing the check-in.
    """
    permission_classes = [CanCheckIn]
    throttle_scope = 'checkin'

    @extend_schema(
        summary="Look up a student for check-in confirmation",
        description=(
            "Resolve a student by QR check_in_token or by unique_code without "
            "recording a check-in. Used by the terminal to show a confirmation "
            "card before committing."
        ),
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'check_in_token': {'type': 'string'},
                    'unique_code': {'type': 'string'},
                },
            },
        },
        responses={
            200: OpenApiResponse(description="Student resolved"),
            400: OpenApiResponse(description="Missing lookup input"),
            404: OpenApiResponse(description="No matching student"),
        },
    )
    def post(self, request):
        token = (request.data.get('check_in_token') or '').strip()
        unique_code = (request.data.get('unique_code') or '').strip()

        if not token and not unique_code:
            return Response(
                {'error': 'Provide check_in_token or unique_code'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        student = None
        method = None
        if token:
            student = Student.objects.filter(check_in_token=token).first()
            method = 'qr'
        if student is None and unique_code:
            student = Student.objects.filter(unique_code__iexact=unique_code).first()
            method = 'manual'

        if student is None:
            return Response(
                {'error': 'No student found for this code.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        enrollment = (
            ClassStudent.objects
            .select_related('class_obj')
            .filter(student=student)
            .first()
        )
        class_name = str(enrollment.class_obj) if enrollment and enrollment.class_obj else None

        already = CheckIn.objects.filter(
            student=student, date=timezone.localdate()
        ).exists()

        return Response({
            'id': student.id,
            'name': student.name,
            'unique_code': student.unique_code,
            'class_name': class_name,
            'checked_in_today': already,
            'method': method,
        }, status=status.HTTP_200_OK)


class StatsView(APIView):
    permission_classes = [IsStaffOrAbove]
    STATS_CACHE_KEY = 'stats_counts'
    STATS_CACHE_TTL = 300  # 5 minutes

    @extend_schema(
        summary="System statistics",
        description="Returns record counts for all tables in the system. Staff and admin only.",
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
    permission_classes = [IsStaffOrAbove]
    ordering = ['id']
    
    def get_queryset(self):
        qs = super().get_queryset()
        teacher_id = self.request.query_params.get('teacher_id')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        status_param = self.request.query_params.get('status')
        subject_id = self.request.query_params.get('subject_id')
        q = (self.request.query_params.get('q') or '').strip()
        
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
        if q:
            qs = qs.filter(
                Q(teacher__name__icontains=q) | Q(subject__name__icontains=q) | Q(status__icontains=q)
            )
        
        return qs

    def destroy(self, request, *args, **kwargs):
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
        with transaction.atomic():
            deleted_count, _ = qs.delete()
        return Response(
            {'deleted_count': deleted_count, 'deleted_ids': ids},
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=['patch'])
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
    permission_classes = [IsStaffOrAbove]
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

    def perform_update(self, serializer):
        # A staff edit supersedes any previous campus check-in auto-mark.
        serializer.save(auto_marked_by_checkin=None)

    @action(detail=False, methods=['post'])
    def bulk_upsert(self, request):
        records = request.data.get('records', request.data)
        if not isinstance(records, list):
            return Response({'error': 'Expected a list of adhoc attendance records'}, status=status.HTTP_400_BAD_REQUEST)

        valid_statuses = {c[0] for c in SessionAttendance.STATUS_CHOICES}
            
        session_ids = set()
        student_ids = set()
        for r in records:
            s_id = r.get('ad_hoc_session_id') or r.get('adhoc_session_id') or r.get('ad_hoc_session') or r.get('adhoc_session')
            st_id = r.get('student_id') or r.get('student')
            if s_id: session_ids.add(int(s_id))
            if st_id: student_ids.add(int(st_id))
            
        existing = {
            (a.ad_hoc_session_id, a.student_id): a
            for a in AdHocSessionAttendance.objects.filter(ad_hoc_session_id__in=session_ids, student_id__in=student_ids)
        }
        
        to_create = []
        to_update = []
        
        with transaction.atomic():
            for r in records:
                s_id = r.get('ad_hoc_session_id') or r.get('adhoc_session_id') or r.get('ad_hoc_session') or r.get('adhoc_session')
                st_id = r.get('student_id') or r.get('student')
                if not s_id or not st_id:
                    continue
                s_id = int(s_id)
                st_id = int(st_id)
                status_val = r.get('status', 'present')
                if status_val not in valid_statuses:
                    return Response(
                        {'error': f'Invalid status "{status_val}". Must be one of {sorted(valid_statuses)}'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                
                key = (s_id, st_id)
                if key in existing:
                    obj = existing[key]
                    obj.status = status_val
                    obj.auto_marked_by_checkin = None
                    to_update.append(obj)
                else:
                    obj = AdHocSessionAttendance(
                        ad_hoc_session_id=s_id,
                        student_id=st_id,
                        status=status_val
                    )
                    to_create.append(obj)
                    
            if to_create:
                AdHocSessionAttendance.objects.bulk_create(to_create)
            if to_update:
                AdHocSessionAttendance.objects.bulk_update(
                    to_update, ['status', 'auto_marked_by_checkin']
                )
                
        return Response({
            'created_count': len(to_create),
            'updated_count': len(to_update)
        }, status=status.HTTP_200_OK)
