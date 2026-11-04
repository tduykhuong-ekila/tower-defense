from django.db import models


class BrowserSessionBlock(models.Model):
    match = models.ForeignKey("matches.Match", on_delete=models.CASCADE)
    credential_hash = models.CharField(max_length=128)
    session_id = models.UUIDField(db_index=True)
    reason = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["match", "credential_hash", "session_id"],
            name="unique_browser_session_block",
        )]
