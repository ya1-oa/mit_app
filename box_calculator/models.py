from django.db import models
from .calculator import CATEGORY_CHOICES
from .ppr_analyzer import PPR_COLUMNS


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


# ---------------------------------------------------------------------------
# PPR (Pre-Packout Report) — AI image-based box count estimation
# ---------------------------------------------------------------------------

class BoxCalcPPRSession(models.Model):
    """
    One PPR per client. Holds room-level AI box count estimates derived from
    photos of the 300-series packout rooms.
    """
    client = models.ForeignKey(
        'docsAppR.Client',
        on_delete=models.CASCADE,
        related_name='ppr_sessions',
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"PPR — {self.client.pOwner} ({self.updated_at:%Y-%m-%d})"

    @property
    def grand_total(self) -> int:
        return sum(r.total for r in self.rooms.all())

    @property
    def grand_counts(self) -> dict:
        totals = {col: 0 for col in PPR_COLUMNS}
        for room in self.rooms.all():
            for col in PPR_COLUMNS:
                totals[col] += getattr(room, col, 0) or 0
        return totals


class BoxCalcPPRRoom(models.Model):
    """
    Per-room PPR box count estimates produced by Claude Vision.
    Each column maps directly to the Excel PPR report format.
    """
    STATUS_CHOICES = [
        ("pending",    "Pending"),
        ("processing", "Processing"),
        ("complete",   "Complete"),
        ("error",      "Error"),
    ]

    session    = models.ForeignKey(BoxCalcPPRSession, on_delete=models.CASCADE, related_name='rooms')
    room_name  = models.CharField(max_length=120)
    order      = models.PositiveIntegerField(default=0)

    # PPR box columns (direct Claude Vision estimates)
    small      = models.PositiveIntegerField(default=0)
    medium     = models.PositiveIntegerField(default=0)
    large      = models.PositiveIntegerField(default=0)
    box_wrapped = models.PositiveIntegerField(default=0)
    plant_vase = models.PositiveIntegerField(default=0)
    tv         = models.PositiveIntegerField(default=0)
    wardrobe   = models.PositiveIntegerField(default=0)
    mattress   = models.PositiveIntegerField(default=0)
    dish_pack  = models.PositiveIntegerField(default=0)
    glass_pack = models.PositiveIntegerField(default=0)
    boots_pans = models.PositiveIntegerField(default=0)

    # Processing metadata
    status          = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    celery_task_id  = models.CharField(max_length=255, blank=True)
    confidence      = models.CharField(max_length=20, blank=True)
    ai_notes        = models.TextField(blank=True)
    images_count    = models.PositiveIntegerField(default=0)
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'room_name']
        unique_together = [('session', 'room_name')]

    def __str__(self):
        return f"{self.room_name} ({self.status})"

    @property
    def total(self) -> int:
        return sum(getattr(self, col, 0) or 0 for col in PPR_COLUMNS)

    def to_dict(self) -> dict:
        counts = {col: getattr(self, col, 0) or 0 for col in PPR_COLUMNS}
        return {
            "id": self.id,
            "room_name": self.room_name,
            "status": self.status,
            "confidence": self.confidence,
            "ai_notes": self.ai_notes,
            "images_count": self.images_count,
            "celery_task_id": self.celery_task_id,
            "counts": counts,
            "total": self.total,
        }
