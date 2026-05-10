"""One-shot config tool for the Phase 9 media live cert (MAIC-917).

Configures the dev tenant's TenantAIConfig with the right shape to
hit OpenRouter's /images/generations endpoint via the OpenAI image
adapter. The OpenAI adapter is wire-compatible with OpenRouter — we
only need to override base_url + model.

Usage:

    OPENROUTER_API_KEY=<your-key> \\
        python manage.py setup_media_cert_tenant --tenant-slug=dev

This is the minimum setup before running:

    curl -X POST -H "Authorization: Bearer <jwt>" \\
         -H "Content-Type: application/json" \\
         -d '{"prompt":"a colourful diagram of fractions"}' \\
         http://localhost:8000/api/maic/v2/media/generate-image/

Discipline: management command only TOUCHES TenantAIConfig — does not
mint JWTs, does not run actual generation. Cert is still user-driven
via curl/browser. Idempotent — re-running with the same args updates
in place rather than failing.
"""
from __future__ import annotations

import os

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Set up a tenant's TenantAIConfig for the Phase 9 media live "
        "cert (MAIC-917) via OpenRouter. Configures image_provider=openai "
        "with image_base_url pointing at OpenRouter's /api/v1 + a chosen "
        "image_model. Requires OPENROUTER_API_KEY in the environment."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--tenant-slug",
            required=True,
            help="Slug of the tenant to configure (e.g. 'dev')",
        )
        parser.add_argument(
            "--image-model",
            default="openai/dall-e-3",
            help=(
                "OpenRouter model id for image generation. "
                "Examples: openai/dall-e-3 (default; $0.04/image), "
                "openai/gpt-image-1, black-forest-labs/flux-1.1-pro, "
                "stability-ai/stable-diffusion-xl. See "
                "https://openrouter.ai/docs#image-generation for the "
                "current model roster."
            ),
        )
        parser.add_argument(
            "--enable-flag",
            action="store_true",
            help=(
                "Also flip Tenant.feature_maic_v2=True so the new "
                "endpoints are reachable for this tenant."
            ),
        )

    def handle(self, *args, **options) -> None:
        from apps.tenants.models import Tenant
        from apps.courses.maic_models import TenantAIConfig

        slug = options["tenant_slug"]
        model_id = options["image_model"]
        enable_flag = options["enable_flag"]

        api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            raise CommandError(
                "OPENROUTER_API_KEY is required in the environment. "
                "Export it (or pass via env var on the invocation) "
                "before running this command."
            )

        try:
            tenant = Tenant.objects.get(slug=slug)
        except Tenant.DoesNotExist as exc:
            raise CommandError(f"tenant with slug={slug!r} not found") from exc

        cfg, created = TenantAIConfig.objects.get_or_create(tenant=tenant)
        cfg.image_provider = "openai"  # OpenAI adapter is wire-compat with OpenRouter
        cfg.image_model = model_id
        cfg.image_base_url = "https://openrouter.ai/api/v1"
        cfg.set_image_api_key(api_key)
        cfg.save()

        if enable_flag and not tenant.feature_maic_v2:
            tenant.feature_maic_v2 = True
            tenant.save(update_fields=["feature_maic_v2"])

        verb = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(
            f"{verb} TenantAIConfig for tenant={slug!r}:\n"
            f"  image_provider     = openai (adapter; wire-compat with OpenRouter)\n"
            f"  image_base_url     = https://openrouter.ai/api/v1\n"
            f"  image_model        = {model_id}\n"
            f"  image_api_key      = <set, Fernet-encrypted, {len(api_key)} chars>\n"
            f"  feature_maic_v2    = {tenant.feature_maic_v2}\n"
            f"\nReady. Next: POST /api/maic/v2/media/generate-image/ "
            f"with the dev JWT."
        ))
