from rest_framework import serializers

from .models import (
    AcademicYear, Term, SubjectOffering, Assessment, AssessmentResult, ReportCard,
)


class TermSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="get_number_display", read_only=True)

    class Meta:
        model = Term
        fields = ["id", "academic_year", "number", "name"]
        read_only_fields = fields


class AcademicYearSerializer(serializers.ModelSerializer):
    terms = TermSerializer(many=True, read_only=True)

    class Meta:
        model = AcademicYear
        fields = ["id", "name", "start_date", "end_date", "terms"]
        read_only_fields = ["id", "terms"]


class SubjectOfferingSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    class_name = serializers.CharField(source="class_obj.__str__", read_only=True)

    class Meta:
        model = SubjectOffering
        fields = ["id", "class_obj", "class_name", "subject", "subject_name", "term",
                  "exam_weight", "quiz_weight", "assignment_weight"]
        read_only_fields = ["id", "subject_name", "class_name"]


class AssessmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Assessment
        fields = ["id", "offering", "title", "kind", "max_marks"]
        read_only_fields = ["id"]


class AssessmentResultSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.name", read_only=True)

    class Meta:
        model = AssessmentResult
        fields = ["id", "assessment", "student", "student_name", "marks", "remarks",
                  "recorded_by", "updated_at"]
        read_only_fields = ["id", "student_name", "recorded_by", "updated_at"]


class ReportCardSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()

    def get_status(self, obj):
        return "published" if obj.published_at else "draft"

    class Meta:
        model = ReportCard
        fields = ["id", "student", "class_obj", "term", "revision", "comments", "snapshot",
                  "status", "created_by", "created_at", "published_at", "published_by"]
        read_only_fields = ["id", "revision", "snapshot", "status", "created_by",
                            "created_at", "published_at", "published_by"]
