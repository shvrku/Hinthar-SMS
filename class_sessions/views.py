from datetime import datetime, timedelta

from rest_framework.viewsets import ModelViewSet
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.utils import timezone
from class_sessions.models import Session, SessionAttendance
from class_sessions.serializers import SessionSerializer, SessionAttendanceSerializer, SessionAttendanceListSerializer
from people.permissions import IsAdmin, IsOwnerTeacher
from timetable.models import TimetableSlot, ClassStudent, TimetableStudent

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
