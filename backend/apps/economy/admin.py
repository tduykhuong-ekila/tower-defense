from django.contrib import admin

from apps.economy.models import CoinTransaction


@admin.register(CoinTransaction)
class CoinTransactionAdmin(admin.ModelAdmin):
    list_display = ["team", "amount", "balance_after", "transaction_type", "reference_id", "created_at"]
    list_filter = ["transaction_type", "match"]
    search_fields = ["team__name", "reference_id", "description"]
