"""Friend serializers."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import FriendRequest

User = get_user_model()


class SendFriendRequestSerializer(serializers.Serializer):
    username = serializers.CharField()


class FriendRequestSerializer(serializers.ModelSerializer):
    sender_id = serializers.IntegerField(source='sender.id', read_only=True)
    sender_username = serializers.CharField(source='sender.username', read_only=True)
    recipient_id = serializers.IntegerField(source='recipient.id', read_only=True)
    recipient_username = serializers.CharField(source='recipient.username', read_only=True)

    class Meta:
        model = FriendRequest
        fields = ('id', 'sender_id', 'sender_username', 'recipient_id',
                  'recipient_username', 'status', 'created_at')


class FriendSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username')


class UserSearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username')
