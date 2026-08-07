"""
Repopulates the database from scratch with:
- Edexcel curriculum subjects (Y6-Y9, IGCSE, IAL)
- Teachers named after HoYoverse + Kuro Games characters
- Students named after HoYoverse + Kuro Games characters
- Classes for Y6 through IAL with cohorts and streams
- Timetable slots (weekly schedule) with realistic period layout
- Sessions generated from timetable slots (past 2 weeks + current week)
- Attendance records for completed sessions
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import connection
from people.models import User, Teacher, Student, Subject
from timetable.models import Class, ClassStudent, TimetableSlot
from class_sessions.models import Session, SessionAttendance, CheckIn, AdHocSession, AdHocSessionAttendance
from datetime import date, timedelta, time, datetime as dt
from decimal import Decimal
import random
import secrets

random.seed(42)

# ──────────────────────────────────────────────
# Edexcel Curriculum Subjects
# ──────────────────────────────────────────────
SUBJECTS = [
    # Core
    'English Language',
    'English Literature',
    'Mathematics',
    'Further Mathematics',
    # Sciences
    'Physics',
    'Chemistry',
    'Biology',
    'Science (Combined)',
    # Humanities
    'History',
    'Geography',
    'Religious Studies',
    # Social Sciences
    'Business Studies',
    'Economics',
    'Accounting',
    # Technology
    'Computer Science',
    'ICT',
    'Design & Technology',
    # Languages
    'French',
    'Spanish',
    # Arts
    'Art & Design',
    'Music',
    'Drama',
]

# ──────────────────────────────────────────────
# Teachers — HoYoverse + Kuro Games characters
# Format: (name, employment_type, rate_unused, [subjects_they_teach])
# rate kept in tuple shape for subject list at index 3; not stored on Teacher.
# ──────────────────────────────────────────────
TEACHERS = [
    # Genshin Impact
    ('Albedo', 'full_time', Decimal('28.00'), ['Chemistry', 'Art & Design']),
    ('Zhongli', 'full_time', Decimal('30.00'), ['History', 'Mathematics']),
    ('Raiden Shogun', 'full_time', Decimal('30.00'), ['Physics', 'Religious Studies']),
    ('Tighnari', 'full_time', Decimal('26.00'), ['Biology', 'Geography']),
    ('Ningguang', 'full_time', Decimal('32.00'), ['Business Studies', 'Economics']),
    ('Yae Miko', 'tutor', Decimal('35.00'), ['English Literature', 'Drama']),
    ('Ayato', 'full_time', Decimal('28.00'), ['English Language', 'History']),
    ('Kazuha', 'tutor', Decimal('25.00'), ['Geography', 'Music']),
    ('Jean', 'full_time', Decimal('29.00'), ['French', 'English Language']),
    ('Sucrose', 'tutor', Decimal('24.00'), ['Chemistry', 'Biology']),
    ('Venti', 'tutor', Decimal('27.00'), ['Music', 'Drama']),
    ('Alhaitham', 'full_time', Decimal('30.00'), ['Mathematics', 'Further Mathematics']),
    ('Xiangling', 'tutor', Decimal('23.00'), ['Design & Technology', 'Art & Design']),
    ('Hu Tao', 'tutor', Decimal('28.00'), ['English Literature', 'Drama']),
    # Honkai: Star Rail
    ('Welt', 'full_time', Decimal('30.00'), ['History', 'English Literature']),
    ('Dr. Ratio', 'full_time', Decimal('32.00'), ['Mathematics', 'Physics']),
    ('Silver Wolf', 'tutor', Decimal('35.00'), ['Computer Science', 'ICT']),
    ('Sunday', 'full_time', Decimal('28.00'), ['Religious Studies', 'English Language']),
    ('Aventurine', 'tutor', Decimal('33.00'), ['Economics', 'Business Studies']),
    ('Jing Yuan', 'full_time', Decimal('29.00'), ['Physics', 'History']),
    ('Topaz', 'tutor', Decimal('34.00'), ['Accounting', 'Business Studies']),
    ('Bronya', 'full_time', Decimal('28.00'), ['Spanish', 'English Language']),
    ('Himeko', 'full_time', Decimal('30.00'), ['Design & Technology', 'Physics']),
    ('Screwllum', 'tutor', Decimal('36.00'), ['Computer Science', 'ICT']),
    ('Acheron', 'tutor', Decimal('28.00'), ['English Literature', 'Religious Studies']),
    # Kuro Games — Wuthering Waves
    ('Jinhsi', 'full_time', Decimal('29.00'), ['Mathematics', 'Science (Combined)']),
    ('Calcharo', 'tutor', Decimal('27.00'), ['Computer Science', 'Design & Technology']),
    ('Yinlin', 'tutor', Decimal('26.00'), ['Music', 'Art & Design']),
    ('Verina', 'full_time', Decimal('25.00'), ['Biology', 'Science (Combined)']),
    ('Jiyan', 'full_time', Decimal('28.00'), ['Physics', 'Geography']),
    # ZZZ
    ('Miyabi', 'tutor', Decimal('30.00'), ['Drama', 'Music']),
]

# ──────────────────────────────────────────────
# Classes — Y6 through IAL
# Format: (education_level, cohort_identifier, cohort_sub_category)
# ──────────────────────────────────────────────
CLASSES = [
    # Year 6
    ('Year6', 'A', None), ('Year6', 'B', None),
    # Year 7
    ('Year7', 'C', None), ('Year7', 'D', None),
    # Year 8
    ('Year8', 'E', None), ('Year8', 'F', None),
    # Year 9
    ('Year9', 'G', None), ('Year9', 'H', None),
    # IGCSE — 3 cohorts x 2 streams
    ('IG', 'K', '1'), ('IG', 'K', '2'),
    ('IG', 'L', '1'), ('IG', 'L', '2'),
    ('IG', 'M', '1'), ('IG', 'M', '2'),
    # IAL — 2 cohorts x 2 streams
    ('IAL', 'N', '1'), ('IAL', 'N', '2'),
    ('IAL', 'P', '1'), ('IAL', 'P', '2'),
]

# ──────────────────────────────────────────────
# Students — HoYoverse + Kuro Games characters
# ──────────────────────────────────────────────
STUDENTS = [
    # Genshin Impact
    'Klee', 'Diona', 'Qiqi', 'Yaoyao', 'Sayu', 'Dori', 'Nahida',
    'Fischl', 'Bennett', 'Razor', 'Barbara', 'Noelle', 'Xingqiu',
    'Chongyun', 'Amber', 'Kaeya', 'Lisa', 'Collei', 'Yun Jin',
    'Yanfei', 'Freminet', 'Mika', 'Lynette', 'Kuki Shinobu',
    'Heizou', 'Gorou', 'Thoma', 'Sara', 'Candace',
    'Nilou', 'Faruzan', 'Layla', 'Kirara', 'Charlotte',
    'Chevreuse', 'Gaming', 'Sethos', 'Ororon', 'Kachina',
    # Honkai: Star Rail
    'March 7th', 'Dan Heng', 'Seele', 'Serval', 'Pela',
    'Sushang', 'Hook', 'Clara', 'Arlan', 'Asta',
    'Qingque', 'Guinaifen', 'Hanya', 'Xueyi',
    'Misha', 'Lynx', 'Firefly', 'Sparkle',
    'Feixiao', 'Moze', 'Tribbie', 'Hyacine',
    # Wuthering Waves
    'Rover (F)', 'Rover (M)', 'Yangyang', 'Chixia', 'Baizhi',
    'Lingyang', 'Encore', 'Sanhua', 'Danjin', 'Yuanwu',
    'Taoqi', 'Youhu', 'Zhezhi', 'Camellya', 'Shorekeeper',
    'Brant', 'Cartethyia', 'Ciaccona', 'Phrolova',
    # ZZZ
    'Anby', 'Nicole', 'Billy', 'Corin', 'Soukaku',
    'Nekomata', 'Piper', 'Lucy', 'Rina', 'Grace Howard',
    'Jane Doe', 'Astra Yao', 'Pulchra', 'Trigger',
]

# Age ranges (approx) per education level for DOB generation
LEVEL_AGE = {
    'Year6': (10, 11), 'Year7': (11, 12), 'Year8': (12, 13),
    'Year9': (13, 14), 'IG': (14, 16), 'IAL': (16, 18),
}

# Period structure for timetable
PERIODS = [
    ('P1', time(8, 0), time(8, 50)),
    ('P2', time(8, 50), time(9, 40)),
    ('P3', time(9, 55), time(10, 45)),
    ('P4', time(10, 45), time(11, 35)),
    # Lunch break
    ('P5', time(12, 20), time(13, 10)),
    ('P6', time(13, 10), time(14, 0)),
    ('P7', time(14, 15), time(15, 5)),
]

# Subjects applicable per education level
LEVEL_SUBJECTS = {
    'Year6': [
        'English Language', 'Mathematics', 'Science (Combined)',
        'History', 'Geography', 'ICT', 'Art & Design', 'Music',
        'French', 'Spanish',
    ],
    'Year7': [
        'English Language', 'English Literature', 'Mathematics',
        'Science (Combined)', 'History', 'Geography', 'ICT',
        'Art & Design', 'Music', 'French', 'Spanish',
        'Religious Studies', 'Drama',
    ],
    'Year8': [
        'English Language', 'English Literature', 'Mathematics',
        'Biology', 'Chemistry', 'Physics', 'History', 'Geography',
        'Computer Science', 'Art & Design', 'Music', 'French',
        'Spanish', 'Religious Studies', 'Drama',
    ],
    'Year9': [
        'English Language', 'English Literature', 'Mathematics',
        'Biology', 'Chemistry', 'Physics', 'History', 'Geography',
        'Computer Science', 'Business Studies', 'Art & Design',
        'Music', 'Design & Technology', 'French', 'Spanish',
        'Religious Studies', 'Drama',
    ],
    'IG': [
        'English Language', 'English Literature', 'Mathematics',
        'Physics', 'Chemistry', 'Biology', 'History', 'Geography',
        'Computer Science', 'Business Studies', 'Economics',
        'Accounting', 'ICT', 'Art & Design', 'French', 'Spanish',
    ],
    'IAL': [
        'Mathematics', 'Further Mathematics', 'Physics', 'Chemistry',
        'Biology', 'Economics', 'Accounting', 'Business Studies',
        'Computer Science', 'English Literature', 'History',
    ],
}

ALL_DAYS = [0, 1, 2, 3, 4]  # Monday-Friday

BULK_SIZE = 500  # batch size for bulk_create


class Command(BaseCommand):
    help = 'Repopulates the entire database with HoYoverse/Kuro-themed Edexcel curriculum data.'

    def _clear_all(self):
        """Truncate all tables in dependency order."""
        self.stdout.write('Clearing existing data...')
        models = [
            CheckIn,
            AdHocSessionAttendance,
            SessionAttendance,
            AdHocSession,
            Session,
            TimetableSlot,
            ClassStudent,
            Class,
            Teacher,
            Student,
            Subject,
        ]
        for model in models:
            cnt, _ = model.objects.all().delete()
            self.stdout.write(f'  Cleared {model.__name__} ({cnt} records)')

        engine = connection.settings_dict['ENGINE']
        if 'sqlite3' in engine:
            with connection.cursor() as cursor:
                for model in models:
                    cursor.execute(
                        f"DELETE FROM sqlite_sequence WHERE name='{model._meta.db_table}'"
                    )
            self.stdout.write('  Reset SQLite auto-increment counters')
        elif 'postgresql' in engine or 'postgis' in engine:
            with connection.cursor() as cursor:
                for model in models:
                    seq_name = f"{model._meta.db_table}_id_seq"
                    cursor.execute(f"ALTER SEQUENCE IF EXISTS {seq_name} RESTART WITH 1;")
            self.stdout.write('  Reset PostgreSQL auto-increment sequence counters to 1')

    def handle(self, *args, **options):
        self._clear_all()

        # ── 1. Subjects ──
        self.stdout.write('\n--- Creating Subjects ---')
        subject_map = {}
        subjects_bulk = [Subject(name=name) for name in SUBJECTS]
        Subject.objects.bulk_create(subjects_bulk, ignore_conflicts=True)
        for subj in Subject.objects.all():
            subject_map[subj.name] = subj
        self.stdout.write(f'  Created {len(subject_map)} Subjects')

        # ── 2. Teachers ──
        self.stdout.write('\n--- Creating Teachers ---')
        from people.utils import generate_unique_code
        teacher_objs = [
            Teacher(name=t[0], employment_type=t[1])
            for t in TEACHERS
        ]
        for t in teacher_objs:
            if not t.unique_code:
                t.unique_code = generate_unique_code(t)
        Teacher.objects.bulk_create(teacher_objs)
        teacher_objs = list(Teacher.objects.all())
        self.stdout.write(f'  Created {len(teacher_objs)} Teachers')

        # ── 3. Classes ──
        self.stdout.write('\n--- Creating Classes ---')
        class_bulk = [
            Class(education_level=cl[0], cohort_identifier=cl[1], cohort_sub_category=cl[2])
            for cl in CLASSES
        ]
        Class.objects.bulk_create(class_bulk)
        class_objs = list(Class.objects.all())
        self.stdout.write(f'  Created {len(class_objs)} Classes')

        # ── 4. Students ──
        self.stdout.write('\n--- Creating Students ---')
        today = date.today()
        shuffled = list(STUDENTS)
        random.shuffle(shuffled)

        student_objs = []
        enrollment_bulk = []
        for i, name in enumerate(shuffled):
            cls = class_objs[i % len(class_objs)]
            edu_level = cls.education_level
            age_min, age_max = LEVEL_AGE.get(edu_level, (14, 16))
            birth_year = today.year - random.randint(age_min, age_max)
            birth_month = random.randint(1, 12)
            birth_day = random.randint(1, 28)
            dob = date(birth_year, birth_month, birth_day)

            student = Student(
                name=name, dob=dob,
                check_in_token=secrets.token_urlsafe(32),
            )
            student.unique_code = generate_unique_code(student)
            student_objs.append(student)

        Student.objects.bulk_create(student_objs)
        student_objs = list(Student.objects.all())

        for i, student in enumerate(student_objs):
            cls = class_objs[i % len(class_objs)]
            enrollment_bulk.append(ClassStudent(class_obj=cls, student=student))

        ClassStudent.objects.bulk_create(enrollment_bulk, ignore_conflicts=True)
        self.stdout.write(f'  Created {len(student_objs)} Students across {len(class_objs)} Classes')

        # ── 5. Timetable Slots ──
        self.stdout.write('\n--- Creating Timetable Slots ---')
        slot_bulk = []
        teacher_pool = list(teacher_objs)

        for cls in class_objs:
            available_subjects = LEVEL_SUBJECTS.get(cls.education_level, SUBJECTS[:10])
            num_subjects = min(len(available_subjects), random.randint(7, 10))
            cls_subjects = random.sample(available_subjects, num_subjects)

            random.shuffle(teacher_pool)
            subj_teacher = {}
            for i, subj_name in enumerate(cls_subjects):
                subj_teacher[subj_name] = teacher_pool[i % len(teacher_pool)]

            for subj_name in cls_subjects:
                occurrences = random.randint(1, 3)
                days = random.sample(ALL_DAYS, occurrences)
                for day in days:
                    period = random.choice(PERIODS)
                    slot_bulk.append(TimetableSlot(
                        class_obj=cls,
                        subject=subject_map[subj_name],
                        teacher=subj_teacher[subj_name],
                        day_of_week=day,
                        start_time=period[1],
                        end_time=period[2],
                        room=f'R{random.randint(101, 310)}',
                    ))

        TimetableSlot.objects.bulk_create(slot_bulk)
        slot_objs = list(TimetableSlot.objects.select_related('class_obj', 'teacher', 'subject'))
        self.stdout.write(f'  Created {len(slot_objs)} Timetable Slots')

        # ── 6. Sessions (2 weeks back + current week) ──
        self.stdout.write('\n--- Creating Sessions ---')
        days_since_monday = today.weekday()
        last_monday = today - timedelta(days=days_since_monday)
        start_monday = last_monday - timedelta(weeks=2)  # only 2 weeks back

        # Build a map: class_obj -> list of its slots
        cls_slot_map = {}
        for slot in slot_objs:
            cls_slot_map.setdefault(slot.class_obj_id, []).append(slot)

        # Build a map: class_obj_id -> list of enrolled student objects
        cls_students_map = {}
        for cs in ClassStudent.objects.select_related('student'):
            cls_students_map.setdefault(cs.class_obj_id, []).append(cs.student)

        session_bulk = []
        attendance_bulk = []

        for cls in class_objs:
            cls_slots = cls_slot_map.get(cls.id, [])
            enrolled = cls_students_map.get(cls.id, [])

            for week_offset in range(3):  # 2 past + 1 current
                week_start = start_monday + timedelta(weeks=week_offset)
                for day_offset in range(5):
                    session_date = week_start + timedelta(days=day_offset)
                    day_slots = [s for s in cls_slots if s.day_of_week == day_offset]

                    for slot in day_slots:
                        start_dt = timezone.make_aware(dt.combine(session_date, slot.start_time))
                        end_dt = timezone.make_aware(dt.combine(session_date, slot.end_time))

                        if session_date < today:
                            status = 'completed' if random.random() < 0.92 else 'cancelled'
                        elif session_date == today:
                            status = random.choice(['scheduled', 'completed'])
                        else:
                            status = 'scheduled'

                        session = Session(
                            timetable_slot=slot,
                            teacher=slot.teacher,
                            class_obj=cls,
                            start_time=start_dt,
                            end_time=end_dt,
                            status=status,
                        )
                        session_bulk.append(session)

                        # Flush sessions in batches to get IDs for attendance
                        if len(session_bulk) >= BULK_SIZE:
                            Session.objects.bulk_create(session_bulk, ignore_conflicts=True)
                            session_bulk.clear()

            # Flush remaining sessions for this class
            if session_bulk:
                Session.objects.bulk_create(session_bulk, ignore_conflicts=True)
                session_bulk.clear()

        # Now create attendance for completed sessions
        self.stdout.write('  Creating Attendance Records...')
        completed_sessions = list(
            Session.objects.filter(status='completed')
            .select_related('class_obj')
            .prefetch_related('class_obj__class_students')
        )

        for session in completed_sessions:
            class_id = session.class_obj_id
            enrolled = cls_students_map.get(class_id, [])
            for student in enrolled:
                att_status = random.choices(
                    ['present', 'absent', 'late'],
                    weights=[75, 15, 10],
                )[0]
                attendance_bulk.append(SessionAttendance(
                    session=session,
                    student=student,
                    status=att_status,
                ))

            if len(attendance_bulk) >= BULK_SIZE:
                SessionAttendance.objects.bulk_create(attendance_bulk, ignore_conflicts=True)
                attendance_bulk.clear()

        if attendance_bulk:
            SessionAttendance.objects.bulk_create(attendance_bulk, ignore_conflicts=True)

        self.stdout.write(f'  Created {Session.objects.count()} Sessions')
        self.stdout.write(f'  Created {SessionAttendance.objects.count()} Attendance Records')

        # ── 7. CheckIns ──
        self.stdout.write('\n--- Creating Check-Ins ---')
        checkin_bulk = []
        # Ensure check-ins only exist for today and past days
        today_checkin_students = random.sample(student_objs, 2)
        for student in today_checkin_students:
            checkin_bulk.append(CheckIn(
                student=student,
                date=today,
                check_in_type='qr',
            ))

        for days_ago in range(1, 7):
            past_date = today - timedelta(days=days_ago)
            day_students = random.sample(student_objs, random.randint(6, 12))
            for student in day_students:
                checkin_bulk.append(CheckIn(
                    student=student,
                    date=past_date,
                    check_in_type=random.choice(['qr', 'manual']),
                ))

        CheckIn.objects.bulk_create(checkin_bulk, ignore_conflicts=True)
        self.stdout.write(f'  Created {CheckIn.objects.count()} Check-Ins')

        # ── Summary ──
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write('POPULATION COMPLETE')
        self.stdout.write('=' * 60)
        self.stdout.write(f'  Subjects:           {Subject.objects.count()}')
        self.stdout.write(f'  Teachers:           {Teacher.objects.count()}')
        self.stdout.write(f'  Students:           {Student.objects.count()}')
        self.stdout.write(f'  Classes:            {Class.objects.count()}')
        self.stdout.write(f'  Class Enrollments:  {ClassStudent.objects.count()}')
        self.stdout.write(f'  Timetable Slots:    {TimetableSlot.objects.count()}')
        self.stdout.write(f'  Sessions:           {Session.objects.count()}')
        self.stdout.write(f'  Attendance Records: {SessionAttendance.objects.count()}')
        self.stdout.write(f'  Check-Ins:          {CheckIn.objects.count()}')
