from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    teacher_id = serializers.PrimaryKeyRelatedField(read_only=True, source='teacher.id')
    student_id = serializers.PrimaryKeyRelatedField(read_only=True, source='student.id')
    
    class Meta:
        model = User
        fields = [
            'id', 
            'username', 
            'email', 
            'role', 
            'clerk_id', 
            'teacher_id', 
            'student_id',
            'is_active'
        ]
        read_only_fields = fields
