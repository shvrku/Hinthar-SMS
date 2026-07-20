from django.core.management.base import BaseCommand
from django.utils import timezone
from people.models import User, Teacher, Student, Subject
from timetable.models import Class, ClassStudent, TimetableSlot
from class_sessions.models import Session, SessionAttendance
# from payroll.models import PayPeriod, Payslip, Adjustment  # Archived
from datetime import date, timedelta, time


class Command(BaseCommand):
    help = 'Populates the database with dummy data'

    def handle(self, *args, **options):
        self.stdout.write('Populating dummy data...')

        # --- People Module ---
        # Subjects
        subjects_data = [
            {'name': 'Mathematics'},
            {'name': 'Physics'},
            {'name': 'Chemistry'},
            {'name': 'Biology'},
            {'name': 'English'},
        ]
        subjects = []
        for data in subjects_data:
            subj, created = Subject.objects.get_or_create(name=data['name'])
            subjects.append(subj)
            if created:
                self.stdout.write(f'Created Subject: {subj.name}')

        # Teachers
        teachers_data = [
            {'name': 'John Smith', 'employment_type': 'full_time', 'default_rate': 25.00},
            {'name': 'Emily Davis', 'employment_type': 'tutor', 'default_rate': 30.00},
            {'name': 'Michael Johnson', 'employment_type': 'full_time', 'default_rate': 28.00},
        ]
        teachers = []
        for data in teachers_data:
            teacher, created = Teacher.objects.get_or_create(
                name=data['name'],
                defaults={
                    'employment_type': data['employment_type'],
                    'default_rate': data['default_rate'],
                }
            )
            teachers.append(teacher)
            if created:
                self.stdout.write(f'Created Teacher: {teacher.name}')

        # Students
        students_data = [
            {'name': 'Alice Brown', 'dob': date(2010, 5, 15)},
            {'name': 'Bob Wilson', 'dob': date(2011, 3, 22)},
            {'name': 'Charlie Taylor', 'dob': date(2010, 8, 30)},
            {'name': 'Diana Anderson', 'dob': date(2011, 1, 10)},
            {'name': 'Ethan Thomas', 'dob': date(2010, 12, 5)},
        ]
        students = []
        for data in students_data:
            student, created = Student.objects.get_or_create(
                name=data['name'],
                defaults={'dob': data['dob']}
            )
            students.append(student)
            if created:
                self.stdout.write(f'Created Student: {student.name}')

        # --- Timetable Module ---
        # Classes
        classes_data = [
            {'education_level': 'IAL', 'cohort_identifier': 'E'},
            {'education_level': 'IG', 'cohort_identifier': 'K'},
            {'education_level': 'Year9', 'cohort_identifier': 'A'},
        ]
        classes = []
        for data in classes_data:
            class_obj, created = Class.objects.get_or_create(
                education_level=data['education_level'],
                cohort_identifier=data['cohort_identifier'],
                cohort_sub_category=None
            )
            classes.append(class_obj)
            if created:
                self.stdout.write(f'Created Class: {class_obj}')

        # Class Students
        for i, student in enumerate(students):
            class_student, created = ClassStudent.objects.get_or_create(
                class_obj=classes[i % len(classes)],
                student=student
            )
            if created:
                self.stdout.write(f'Enrolled {student.name} in {class_student.class_obj}')

        # Timetable Slots
        timetable_slots_data = [
            {
                'class_obj': classes[0],
                'subject': subjects[0],
                'teacher': teachers[0],
                'day_of_week': 0,
                'start_time': time(9, 0),
                'end_time': time(10, 0),
            },
            {
                'class_obj': classes[0],
                'subject': subjects[1],
                'teacher': teachers[1],
                'day_of_week': 1,
                'start_time': time(10, 0),
                'end_time': time(11, 0),
            },
            {
                'class_obj': classes[1],
                'subject': subjects[2],
                'teacher': teachers[2],
                'day_of_week': 2,
                'start_time': time(11, 0),
                'end_time': time(12, 0),
            },
            {
                'class_obj': classes[2],
                'subject': subjects[3],
                'teacher': teachers[1],
                'day_of_week': 3,
                'start_time': time(14, 0),
                'end_time': time(15, 0),
            },
        ]
        timetable_slots = []
        for data in timetable_slots_data:
            slot, created = TimetableSlot.objects.get_or_create(
                class_obj=data['class_obj'],
                subject=data['subject'],
                teacher=data['teacher'],
                day_of_week=data['day_of_week'],
                start_time=data['start_time'],
                defaults={'end_time': data['end_time']}
            )
            timetable_slots.append(slot)
            if created:
                self.stdout.write(f'Created Timetable Slot: {slot}')

        # --- Sessions & Attendance Module ---
        from datetime import datetime as dt
        today = date.today()
        for i in range(10):
            session_date = today - timedelta(days=i)
            for slot in timetable_slots:
                start_time = timezone.make_aware(dt.combine(session_date, slot.start_time))
                end_time = timezone.make_aware(dt.combine(session_date, slot.end_time))
                session, created = Session.objects.get_or_create(
                    timetable_slot=slot,
                    start_time=start_time,
                    defaults={
                        'end_time': end_time,
                        'teacher': slot.teacher,
                        'class_obj': slot.class_obj,
                        'status': 'completed' if i > 2 else 'scheduled',
                        'paid': i > 5
                    }
                )
                if created:
                    self.stdout.write(f'Created Session: {session}')

                    # Attendance from class roster
                    if session.class_obj:
                        class_students = ClassStudent.objects.filter(class_obj=session.class_obj)
                        for cs in class_students:
                            SessionAttendance.objects.get_or_create(
                                session=session,
                                student=cs.student,
                                defaults={'status': 'absent'}
                            )

        # # --- Payroll Module (Archived) ---
        # # Pay Periods
        # pay_period, created = PayPeriod.objects.get_or_create(
        #     start_date=today - timedelta(days=30),
        #     end_date=today
        # )
        # if created:
        #     self.stdout.write(f'Created Pay Period: {pay_period}')

        # # Payslips
        # for teacher in teachers:
        #     session_count = Session.objects.filter(
        #         teacher=teacher,
        #         start_time__date__range=(pay_period.start_date, pay_period.end_date),
        #         status='completed',
        #         paid=False
        #     ).count()
        #     if session_count > 0:
        #         from decimal import Decimal
        #         gross_pay = session_count * teacher.default_rate
        #         tax = gross_pay * Decimal('0.15')
        #         net = gross_pay - tax
        #         payslip, created = Payslip.objects.get_or_create(
        #             teacher=teacher,
        #             pay_period=pay_period,
        #             defaults={
        #                 'session_count': session_count,
        #                 'rate_applied': teacher.default_rate,
        #                 'gross_pay': gross_pay,
        #                 'tax_deduction': tax,
        #                 'net_pay': net,
        #                 'status': 'approved'
        #             }
        #         )
        #         if created:
        #             self.stdout.write(f'Created Payslip: {payslip}')

        #             Session.objects.filter(
        #                 teacher=teacher,
        #                 start_time__date__range=(pay_period.start_date, pay_period.end_date),
        #                 status='completed',
        #                 paid=False
        #             ).update(paid=True, payslip=payslip)

        self.stdout.write('Dummy data populated successfully!')
