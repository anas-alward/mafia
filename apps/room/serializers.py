"""Room serializers."""

from __future__ import annotations

from typing import Any

from django.db import models as db_models
from rest_framework import serializers

from .models import Room, RoomJoinRequest, RoomMember


class CreateRoomSerializer(serializers.ModelSerializer):
    scheduled_at = serializers.DateTimeField(required=False, allow_null=True)
    role_configuration = serializers.JSONField(required=False, default=dict)

    class Meta:
        model = Room
        fields = ('name', 'max_members', 'scheduled_at', 'role_configuration')

    def validate_max_members(self, value: int) -> int:
        if value < 4 or value > 20:
            raise serializers.ValidationError('Must be between 4 and 20.')
        return value


class RoomSerializer(serializers.ModelSerializer):
    host = serializers.StringRelatedField()
    member_count = serializers.IntegerField(read_only=True)
    members = serializers.SerializerMethodField()

    class Meta:
        model = Room
        fields = (
            'id', 'name', 'code', 'host', 'max_members',
            'member_count', 'status', 'meeting_id',
            'scheduled_at', 'role_configuration',
            'created_at', 'updated_at', 'members',
        )

    def get_members(self, obj: Room) -> list[dict[str, Any]]:
        return list(
            RoomMember.objects
            .filter(room=obj)
            .select_related('user')
            .annotate(username=db_models.F('user__username'))
            .values('user_id', 'username', 'joined_at', 'added_by')
        )


class JoinRequestSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = RoomJoinRequest
        fields = ('id', 'user_id', 'username', 'status', 'requested_at')
