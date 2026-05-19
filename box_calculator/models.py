from django.db import models
from .calculator import CATEGORY_CHOICES


class BoxCalcSession(models.Model):
    client = models.ForeignKey(
        'docsAppR.Client',
        on_delete=models.CASCADE,
        related_name='box_calc_sessions',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"Box Calc — {self.client.pOwner} ({self.updated_at:%Y-%m-%d})"

    def get_job_report(self):
        from .calculator import Room, Item, ItemCategory, calculate_job
        rooms = []
        for bcr in self.rooms.prefetch_related('items').all():
            items = tuple(
                Item(
                    category=ItemCategory(i.category),
                    quantity=i.quantity,
                    compartments=i.compartments,
                    note=i.note,
                )
                for i in bcr.items.all()
            )
            rooms.append(Room(name=bcr.room_name, items=items))
        return calculate_job(rooms)


class BoxCalcRoom(models.Model):
    session = models.ForeignKey(
        BoxCalcSession,
        on_delete=models.CASCADE,
        related_name='rooms',
    )
    room = models.ForeignKey(
        'docsAppR.Room',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='box_calc_rooms',
    )
    room_name = models.CharField(max_length=100)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'room_name']

    def __str__(self):
        return self.room_name

    def get_report(self):
        from .calculator import Room, Item, ItemCategory, calculate_room
        items = tuple(
            Item(
                category=ItemCategory(i.category),
                quantity=i.quantity,
                compartments=i.compartments,
                note=i.note,
            )
            for i in self.items.all()
        )
        return calculate_room(Room(name=self.room_name, items=items))


class BoxCalcItem(models.Model):
    room = models.ForeignKey(
        BoxCalcRoom,
        on_delete=models.CASCADE,
        related_name='items',
    )
    category = models.CharField(max_length=40, choices=CATEGORY_CHOICES)
    quantity = models.PositiveIntegerField(default=1)
    compartments = models.PositiveIntegerField(default=0)
    note = models.CharField(max_length=255, blank=True)
    ai_suggested = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'category']

    def __str__(self):
        return f"{self.category} ×{self.quantity}"
