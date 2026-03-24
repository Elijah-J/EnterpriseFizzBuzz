"""FizzBuzz-as-a-Service (FBaaS) events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("FBAAS_TENANT_CREATED")
EventType.register("FBAAS_TENANT_SUSPENDED")
EventType.register("FBAAS_QUOTA_CHECKED")
EventType.register("FBAAS_QUOTA_EXCEEDED")
EventType.register("FBAAS_BILLING_CHARGED")
EventType.register("FBAAS_WATERMARK_APPLIED")
