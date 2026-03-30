"""Stripe Webhook handler.

POST /api/stripe-webhook
Handles checkout.session.completed to update user plan in Supabase.

Requires env vars:
  STRIPE_SECRET_KEY
  STRIPE_WEBHOOK_SECRET
  SUPABASE_SERVICE_ROLE_KEY
  NEXT_PUBLIC_SUPABASE_URL
"""

from http.server import BaseHTTPRequestHandler
import json
import os


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            import stripe
        except ImportError:
            self._json_response(500, {"error": "stripe package not installed"})
            return

        stripe_key = os.environ.get("STRIPE_SECRET_KEY")
        webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET")

        if not stripe_key or not webhook_secret:
            self._json_response(500, {"error": "Stripe not configured"})
            return

        stripe.api_key = stripe_key

        # Read raw body for signature verification
        content_length = int(self.headers.get("Content-Length", 0))
        payload = self.rfile.read(content_length)
        sig_header = self.headers.get("Stripe-Signature", "")

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret
            )
        except (ValueError, stripe.SignatureVerificationError) as e:
            self._json_response(400, {"error": f"Webhook verification failed: {e}"})
            return

        # Handle checkout completion
        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            customer_id = session.get("customer")
            plan = session.get("metadata", {}).get("plan", "pro")
            subscription_id = session.get("subscription")
            customer_email = session.get("customer_details", {}).get("email")

            self._update_plan(customer_id, customer_email, plan, subscription_id)

        elif event["type"] == "customer.subscription.deleted":
            subscription = event["data"]["object"]
            customer_id = subscription.get("customer")
            self._downgrade_to_free(customer_id)

        self._json_response(200, {"received": True})

    def _update_plan(self, customer_id, email, plan, subscription_id):
        """Update user plan in Supabase."""
        supabase_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
        service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

        if not supabase_url or not service_key:
            return

        try:
            import urllib.request

            # Update profiles table by email
            if email:
                data = json.dumps({
                    "plan": plan,
                    "stripe_customer_id": customer_id,
                }).encode()

                req = urllib.request.Request(
                    f"{supabase_url}/rest/v1/profiles?email=eq.{email}",
                    data=data,
                    method="PATCH",
                    headers={
                        "Content-Type": "application/json",
                        "apikey": service_key,
                        "Authorization": f"Bearer {service_key}",
                        "Prefer": "return=minimal",
                    },
                )
                urllib.request.urlopen(req)

        except Exception:
            pass  # Log in production

    def _downgrade_to_free(self, customer_id):
        """Downgrade user to free plan when subscription is cancelled."""
        supabase_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
        service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

        if not supabase_url or not service_key or not customer_id:
            return

        try:
            import urllib.request

            data = json.dumps({"plan": "free"}).encode()
            req = urllib.request.Request(
                f"{supabase_url}/rest/v1/profiles?stripe_customer_id=eq.{customer_id}",
                data=data,
                method="PATCH",
                headers={
                    "Content-Type": "application/json",
                    "apikey": service_key,
                    "Authorization": f"Bearer {service_key}",
                    "Prefer": "return=minimal",
                },
            )
            urllib.request.urlopen(req)
        except Exception:
            pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Stripe-Signature")
        self.end_headers()

    def _json_response(self, status, data):
        body = json.dumps(data)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))
