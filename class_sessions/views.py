from datetime import datetime, timedelta

from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiResponse
from django.db import transaction
from django.utils import timezone
from django.core.cache import cache
from class_sessions.models import Session, SessionAttendance, CheckIn
from class_sessions.serializers import (
    SessionSerializer, SessionAttendanceSerializer,
    SessionAttendanceListSerializer, CheckInSerializer,
)
from people.permissions import IsAdmin, IsOwnerTeacher, CanCheckIn, IsAuthenticatedNonTerminal, IsTerminalOrAbove
from people.models import Student, User, Teacher, Staff, Subject
from timetable.models import TimetableSlot, ClassStudent, TimetableStudent, Class

class SessionViewSet(ModelViewSet):
    queryset = Session.objects.all()
    serializer_class = SessionSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        qs = super().get_queryset()
        teacher_id = self.request.query_params.get('teacher_id')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        
        if teacher_id:
            qs = qs.filter(teacher_id=teacher_id)
        if date_from:
            qs = qs.filter(start_time__date__gte=date_from)
        if date_to:
            qs = qs.filter(start_time__date__lte=date_to)
        
        return qs
    
    def get_permissions(self):
        if self.action in ['create', 'destroy']:
            return [IsAdmin()]
        return [IsAuthenticated()]
    
    @action(detail=True, methods=['patch'], permission_classes=[IsOwnerTeacher])
    def status(self, request, pk=None):
        session = self.get_object()
        new_status = request.data.get('status')
        if new_status:
            session.status = new_status
            session._audit_user = request.user
            session.save()
            serializer = self.get_serializer(session)
            return Response(serializer.data)
        return Response({'error': 'status is required'}, status=400)

class SessionAttendanceViewSet(ModelViewSet):
    queryset = SessionAttendance.objects.select_related(
        'session', 'session__teacher', 'session__class_obj', 'session__timetable_slot',
        'student'
    ).all()
    serializer_class = SessionAttendanceSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [(IsAdmin | IsOwnerTeacher)()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'list':
            return SessionAttendanceListSerializer
        return SessionAttendanceSerializer

class GenerateSessionsView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(
        summary="Generate sessions",
        description="Batch-generate dated sessions from timetable templates for a date range.",
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'start_date': {'type': 'string', 'format': 'date', 'description': 'Defaults to today'},
                    'end_date': {'type': 'string', 'format': 'date', 'description': 'Defaults to start_date + 14 days'},
                },
            },
        },
        responses={
            200: {
                'type': 'object',
                'properties': {'created_sessions': {'type': 'integer'}},
            },
        },
    )
    @transaction.atomic
    def post(self, request):
        start_date = request.data.get('start_date', timezone.localdate())
        end_date = request.data.get('end_date', start_date + timedelta(days=14))
        
        slots = TimetableSlot.objects.select_related('teacher', 'class_obj').all()
        created_count = 0
        
        for slot in slots:
            current_date = start_date
            while current_date <= end_date:
                if current_date.weekday() == slot.day_of_week:
                    start_time = timezone.make_aware(datetime.combine(current_date, slot.start_time))
                    end_time = timezone.make_aware(datetime.combine(current_date, slot.end_time))
                    
                    session, created = Session.objects.get_or_create(
                        timetable_slot=slot,
                        start_time=start_time,
                        defaults={
                            'end_time': end_time,
                            'teacher': slot.teacher,
                            'class_obj': slot.class_obj,
                            'status': 'scheduled',
                            'paid': False
                        }
                    )
                    if created:
                        created_count += 1
                        # Populate attendance roster (default: absent until checked in)
                        if slot.class_obj:
                            class_students = ClassStudent.objects.filter(class_obj=slot.class_obj)
                            for cs in class_students:
                                SessionAttendance.objects.get_or_create(
                                    session=session,
                                    student=cs.student,
                                    defaults={'status': 'absent'}
                                )
                        else:
                            timetable_students = TimetableStudent.objects.filter(timetable_slot=slot)
                            for ts in timetable_students:
                                SessionAttendance.objects.get_or_create(
                                    session=session,
                                    student=ts.student,
                                    defaults={'status': 'absent'}
                                )
                current_date += timedelta(days=1)
        
        return Response({'created_sessions': created_count})


class CheckInViewSet(ReadOnlyModelViewSet):
    queryset = CheckIn.objects.select_related('student', 'checked_by').all()
    serializer_class = CheckInSerializer
    permission_classes = [IsAuthenticatedNonTerminal]


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
                    'timetable_students': {'type': 'integer'},
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
            'timetable_students': TimetableStudent,
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

        serializer = CheckInSerializer(checkin)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
