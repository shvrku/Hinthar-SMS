from rest_framework.viewsets import ModelViewSet
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum
from datetime import timedelta
from class_sessions.models import Session, SessionAttendance
from class_sessions.serializers import SessionSerializer, SessionAttendanceSerializer
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
            qs = qs.filter(session_date__gte=date_from)
        if date_to:
            qs = qs.filter(session_date__lte=date_to)
        
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
            session.save()
            serializer = self.get_serializer(session)
            return Response(serializer.data)
        return Response({'error': 'status is required'}, status=400)

class SessionAttendanceViewSet(ModelViewSet):
    queryset = SessionAttendance.objects.all()
    serializer_class = SessionAttendanceSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [(IsAdmin | IsOwnerTeacher)()]
        return [IsAuthenticated()]

class GenerateSessionsView(APIView):
    permission_classes = [IsAdmin]
    
    @transaction.atomic
    def post(self, request):
        # Generate sessions for the next 2 weeks (or custom date range)
        start_date = request.data.get('start_date', timezone.localdate())
        end_date = request.data.get('end_date', start_date + timedelta(days=14))
        
        slots = TimetableSlot.objects.all()
        created_count = 0
        
        for slot in slots:
            # For each timetable slot, find all days in [start_date, end_date] that match day_of_week
            current_date = start_date
            while current_date <= end_date:
                if current_date.weekday() == slot.day_of_week:
                    # Get or create session for this slot + date
                    session, created = Session.objects.get_or_create(
                        timetable_slot=slot,
                        session_date=current_date,
                        defaults={
                            'teacher': slot.teacher,
                            'class_obj': slot.class_obj,
                            'status': 'scheduled',
                            'paid': False
                        }
                    )
                    if created:
                        created_count += 1
                        # Populate attendance roster
                        if slot.class_obj:
                            # Get all students in the class
                            class_students = ClassStudent.objects.filter(class_obj=slot.class_obj)
                            for cs in class_students:
                                SessionAttendance.objects.get_or_create(
                                    session=session,
                                    student=cs.student,
                                    defaults={'status': 'present'}
                                )
                        else:
                            # Get all students in timetable students
                            timetable_students = TimetableStudent.objects.filter(timetable_slot=slot)
                            for ts in timetable_students:
                                SessionAttendance.objects.get_or_create(
                                    session=session,
                                    student=ts.student,
                                    defaults={'status': 'present'}
                                )
                current_date += timedelta(days=1)
        
        return Response({'created_sessions': created_count})
