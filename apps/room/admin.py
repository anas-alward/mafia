from django.contrib import admin

from .models import Room


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'host', 'max_members', 'status', 'created_at')
    readonly_fields = ('code', 'created_at', 'updated_at')
    search_fields = ('name', 'code', 'host__username')
    list_filter = ('status',)
