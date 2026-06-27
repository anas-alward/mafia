"""Room serializers."""

from __future__ import annotations

from rest_framework import serializers

from .models import Room


class CreateRoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = ('name', 'max_members', 'scheduled_at', 'role_configuration')
        extra_kwargs = {
            'name': {'required': False, 'default': 'New Room'},
            'max_members': {'required': False, 'default': 8},
            'scheduled_at': {'required': False, 'allow_null': True},
            'role_configuration': {'required': False, 'default': dict},
        }



class RoomSerializer(serializers.ModelSerializer):
    host = serializers.StringRelatedField()

    class Meta:
        model = Room
        fields = (
            'id', 'name', 'code', 'host', 'max_members',
            'status', 'meeting_id', 'scheduled_at',
            'role_configuration', 'created_at', 'updated_at',
        )
