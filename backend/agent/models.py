from django.db import models
from django.contrib.auth.models import User
from pgvector.django import VectorField
from django.utils import timezone


class Conversation(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Conversation {self.id} — {self.user.username}"


class Message(models.Model):
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
    ]
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.role}: {self.content[:50]}"


class Memory(models.Model):
    MEMORY_TYPES = [
        ('episodic', 'Episodic'),      # specific events and experiences
        ('semantic', 'Semantic'),       # general facts and knowledge
        ('procedural', 'Procedural'),   # how to do things
        ('temporal', 'Temporal'),       # time-based information
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    key = models.CharField(max_length=255)
    value = models.TextField()
    memory_type = models.CharField(
        max_length=20,
        choices=MEMORY_TYPES,
        default='semantic'
    )
    confidence_score = models.FloatField(default=0.5)
    access_count = models.IntegerField(default=0)
    context_tags = models.JSONField(default=list)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_accessed = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'key')
        ordering = ['-confidence_score', '-last_accessed']

    def __str__(self):
        return f"{self.user.username} — [{self.memory_type}] {self.key}: {self.value[:50]}"

    def reinforce(self, amount=0.1):
        """Increase confidence when memory is confirmed or reused."""
        self.confidence_score = min(1.0, self.confidence_score + amount)
        self.access_count += 1
        self.save()

    def decay(self, amount=0.05):
        """Decrease confidence over time if not accessed."""
        self.confidence_score = max(0.0, self.confidence_score - amount)
        self.save()

    def is_expired(self):
        """Check if memory has expired."""
        if self.expires_at and timezone.now() > self.expires_at:
            return True
        return False


class AutonomousDecision(models.Model):
    OUTCOME_CHOICES = [
        ('success', 'Success'),
        ('failure', 'Failure'),
        ('pending', 'Pending'),
        ('rejected', 'Rejected by user'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    context = models.JSONField(default=dict)
    decision_made = models.JSONField(default=dict)
    risk_score = models.FloatField(default=0.0)
    outcome = models.CharField(
        max_length=20,
        choices=OUTCOME_CHOICES,
        default='pending'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} — {self.outcome} (risk: {self.risk_score})"


class ScheduledTask(models.Model):
    STATUS_CHOICES = [
        ('ok', 'Ok'),
        ('error', 'Error'),
        ('never', 'Never run'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    task_type = models.CharField(max_length=50, default='chat')
    cron_schedule = models.CharField(max_length=100)
    action = models.JSONField(default=dict)
    enabled = models.BooleanField(default=True)
    last_run = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='never')
    last_result = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} — {self.name} ({self.cron_schedule})"
    
class Task(models.Model):
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    deadline = models.DateTimeField(null=True, blank=True)
    deadline_notified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-priority', 'deadline', '-created_at']

    def __str__(self):
        return f"{self.user.username} — {self.title} [{self.priority}]"

    def is_overdue(self):
        from django.utils import timezone
        if self.deadline and self.status == 'pending':
            return timezone.now() > self.deadline
        return False

class Assignment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
    ]

    SUBJECT_CHOICES = [
        ('cs', 'Computer Science'),
        ('humanitarian', 'Humanitarian'),
        ('other', 'Other'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    topic = models.TextField()
    subject_type = models.CharField(max_length=20, choices=SUBJECT_CHOICES, default='cs')
    word_count = models.IntegerField(default=1000)
    deadline = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    outline = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} — {self.title} [{self.status}]"


class AssignmentDraft(models.Model):
    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name='drafts'
    )
    version = models.IntegerField(default=1)
    content = models.TextField()
    word_count_actual = models.IntegerField(default=0)
    file_path = models.CharField(max_length=500, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-version']

    def __str__(self):
        return f"{self.assignment.title} — v{self.version}"        
    
class Trip(models.Model):
    STATUS_CHOICES = [
        ('planning', 'Planning'),
        ('confirmed', 'Confirmed'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    destination = models.CharField(max_length=255)
    purpose = models.CharField(max_length=255, blank=True, null=True)
    departure_date = models.DateField(null=True, blank=True)
    return_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planning')
    itinerary = models.TextField(blank=True, null=True)
    file_path = models.CharField(max_length=500, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-departure_date']

    def __str__(self):
        return f"{self.user.username} — {self.destination} ({self.departure_date})"    

class SelfChunk(models.Model):
    """A chunk of Ash's self-knowledge document, with its embedding.

    Written only by `manage.py index_self`; read by the search_self tool.
    """
    source = models.CharField(max_length=255, default="ASH_SELF.md")
    heading = models.CharField(max_length=500)
    ordinal = models.IntegerField(default=0)
    content = models.TextField()
    embedding = VectorField(dimensions=384)
    indexed_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['source', 'ordinal']
        unique_together = ('source', 'ordinal')

    def __str__(self):
        return f"{self.source} #{self.ordinal} — {self.heading}"
