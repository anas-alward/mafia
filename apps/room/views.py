from rest_framework import generics, permissions, status
from rest_framework.response import Response
from django.contrib.auth import get_user_model

from .realtime import add_participant, create_meeting, remove_participant
from .models import Room
from .serializers import CreateRoomSerializer, RoomSerializer

User = get_user_model()


def _save_participant(room, user_id, participant_id):
    room.participant_ids[str(user_id)] = participant_id
    Room.objects.filter(pk=room.pk).update(participant_ids=room.participant_ids)


def _pop_participant(room, user_id):
    cf_id = room.participant_ids.pop(str(user_id), None)
    Room.objects.filter(pk=room.pk).update(participant_ids=room.participant_ids)
    return cf_id


class CreateRoomView(generics.CreateAPIView):
    queryset = Room.objects.all()
    serializer_class = CreateRoomSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        room = serializer.save(host=request.user)

        meeting_id = create_meeting(room.name)
        room.meeting_id = meeting_id
        room.save(update_fields=['meeting_id'])

        credentials = add_participant(
            meeting_id=meeting_id,
            participant_id=str(request.user.id),
            name=request.user.username,
        )
        _save_participant(room, request.user.id, credentials['participant_id'])

        return Response({
            'room': RoomSerializer(room).data,
            'participant_id': credentials['participant_id'],
            'token': credentials['token'],
        }, status=status.HTTP_201_CREATED)


class JoinRoomView(generics.GenericAPIView):
    queryset = Room.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, code):
        try:
            room = Room.objects.get(code=code)
        except Room.DoesNotExist:
            return Response(
                {'error': 'Room not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if room.status != Room.Status.WAITING:
            return Response(
                {'error': 'Game already started'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if room.members.count() >= room.max_members:
            return Response(
                {'error': 'Room is full'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if room.members.filter(id=request.user.id).exists():
            return Response(
                {'error': 'Already a member of this room'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        room.members.add(request.user)

        credentials = add_participant(
            meeting_id=room.meeting_id,
            participant_id=str(request.user.id),
            name=request.user.username,
            preset_name='group_call_participant',
        )
        _save_participant(room, request.user.id, credentials['participant_id'])

        return Response({
            'room': RoomSerializer(room).data,
            'participant_id': credentials['participant_id'],
            'token': credentials['token'],
        })


class AddMemberView(generics.GenericAPIView):
    queryset = Room.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, code):
        try:
            room = Room.objects.get(code=code)
        except Room.DoesNotExist:
            return Response(
                {'error': 'Room not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if room.host_id != request.user.id:
            return Response(
                {'error': 'Only the host can add members'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if room.status != Room.Status.WAITING:
            return Response(
                {'error': 'Game already started'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if room.members.count() >= room.max_members:
            return Response(
                {'error': 'Room is full'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user_id = request.data.get('user_id')
        if not user_id:
            return Response(
                {'error': 'user_id is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if room.members.filter(id=user.id).exists():
            return Response(
                {'error': 'User is already a member'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        room.members.add(user)

        credentials = add_participant(
            meeting_id=room.meeting_id,
            participant_id=str(user.id),
            name=user.username,
            preset_name='group_call_participant',
        )
        _save_participant(room, user.id, credentials['participant_id'])

        return Response({
            'room': RoomSerializer(room).data,
            'user_id': user.id,
            'username': user.username,
            'participant_id': credentials['participant_id'],
            'token': credentials['token'],
        })


class MemberListView(generics.GenericAPIView):
    queryset = Room.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, code):
        try:
            room = Room.objects.get(code=code)
        except Room.DoesNotExist:
            return Response(
                {'error': 'Room not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not room.members.filter(id=request.user.id).exists() and room.host_id != request.user.id:
            return Response(
                {'error': 'You are not a member of this room'},
                status=status.HTTP_403_FORBIDDEN,
            )

        members = room.members.values('id', 'username')
        return Response({
            'host': {'id': room.host_id, 'username': room.host.username},
            'member_count': room.members.count(),
            'max_members': room.max_members,
            'members': list(members),
        })


class RemoveMemberView(generics.GenericAPIView):
    queryset = Room.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, code):
        try:
            room = Room.objects.get(code=code)
        except Room.DoesNotExist:
            return Response(
                {'error': 'Room not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if room.host_id != request.user.id:
            return Response(
                {'error': 'Only the host can remove members'},
                status=status.HTTP_403_FORBIDDEN,
            )

        user_id = request.data.get('user_id')
        if not user_id:
            return Response(
                {'error': 'user_id is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if str(user_id) == str(request.user.id):
            return Response(
                {'error': 'Cannot remove yourself as host'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not room.members.filter(id=user.id).exists():
            return Response(
                {'error': 'User is not a member of this room'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        room.members.remove(user)

        cf_participant_id = _pop_participant(room, user.id)
        if cf_participant_id:
            remove_participant(
                meeting_id=room.meeting_id,
                participant_id=cf_participant_id,
            )

        return Response({
            'room': RoomSerializer(room).data,
            'removed_user_id': user.id,
            'removed_username': user.username,
        })
