from django.contrib import admin

from .models import GameSession, Participant


@admin.register(GameSession)
class GameSessionAdmin(admin.ModelAdmin):
    list_display = ('room', 'round_number', 'winner', 'started_at', 'ended_at')
    readonly_fields = ('started_at',)
    search_fields = ('room__name', 'room__code')
    list_filter = ('winner',)


@admin.register(Participant)
class ParticipantAdmin(admin.ModelAdmin):
    list_display = ('user', 'game_session', 'role', 'is_alive', 'won')
    list_filter = ('role', 'is_alive', 'won')
    search_fields = ('user__username',)
