from rest_framework import serializers

from .models import Room


class CreateRoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = ('name', 'max_members')

    def validate_max_members(self, value):
        if value < 4 or value > 20:
            raise serializers.ValidationError("Must be between 4 and 20.")
        return value


class RoomSerializer(serializers.ModelSerializer):
    host = serializers.StringRelatedField()
    member_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Room
        fields = (
            'id', 'name', 'code', 'host', 'max_members',
            'member_count', 'status', 'meeting_id',
            'created_at', 'updated_at',
        )
