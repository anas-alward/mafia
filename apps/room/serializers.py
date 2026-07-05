"""Room serializers."""

from __future__ import annotations

from rest_framework import serializers

from .models import Room


class CreateRoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = ('name',)
        extra_kwargs = {'name': {'required': False, 'default': 'New Room'}}


class RoomSerializer(serializers.ModelSerializer):
    host = serializers.StringRelatedField()

    class Meta:
        model = Room
        fields = (
            'id',
            'name',
            'code',
            'host',
            'meeting_id',
        )
