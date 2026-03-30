"""Stripe billing: checkout + webhook in one endpoint.

POST /api/billing
  Body: { "action": "checkout", "plan": "pro" | "business" }
  Body: raw Stripe webhook payload (detected by Stripe-Signature header)
"""

from http.server import BaseHTTPRequestHandler
import json
import os

PRICE_IDS = {
    "pro": os.environ.get("STRIPE_PRO_PRICE_ID", ""),
    "business": os.environ.get("STRIPE_BUSINESS_PRICE_ID", ""),
}


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length)

        # Detect webhook vs checkout by Stripe-Signature header
        sig_header = self.headers.get("Stripe-Signature", "")
        if sig_header:
            self._handle_webhook(raw_body, sig_header)
        else:
            self._handle_checkout(raw_body)

    def _handle_checkout(self, raw_body):
        try:
            import stripe
        except ImportError:
            self._json(500, {"error": "stripe package not installed"})
            return

        stripe_key = os.environ.get("STRIPE_SECRET_KEY")
        if not stripe_key:
            self._json(500, {"error": "STRIPE_SECRET_KEY not configured"})
            return
        stripe.api_key = stripe_key

        try:
            body = json.loads(raw_body) if raw_body else {}
        except (json.JSONDecodeError, ValueError):
            self._json(400, {"error": "Invalid JSON"})
            return

        plan = body.get("plan", "")
        if plan not in ("pro", "business"):
            self._json(400, {"error": "Invalid plan. Must be 'pro' or 'business'"})
            return

        price_id = PRICE_IDS.get(plan)
        if not price_id:
            self._json(500, {"error": f"Price ID not configured for plan: {plan}"})
            return

        origin = self.headers.get("Origin", "https://faultray.com")
        try:
            session = stripe.checkout.Session.create(
                mode="subscription",
                line_items=[{"price": price_id, "quantity": 1}],
                success_url=f"{origin}/dashboard?checkout=success&plan={plan}",
                cancel_url=f"{origin}/pricing?checkout=cancelled",
                metadata={"plan": plan},
            )
            self._json(200, {"url": session.url})
        except Exception as e:
            self._json(400, {"error": str(e)})

    def _handle_webhook(self, payload, sig_header):
        try:
            import stripe
        except ImportError:
            self._json(500, {"error": "stripe package not installed"})
            return

        stripe_key = os.environ.get("STRIPE_SECRET_KEY")
        webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
        if not stripe_key or not webhook_secret:
            self._json(500, {"error": "Stripe not configured"})
            return
        stripe.api_key = stripe_key

        try:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        except (ValueError, stripe.SignatureVerificationError) as e:
            self._json(400, {"error": f"Webhook verification failed: {e}"})
            return

        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            customer_id = session.get("customer")
            plan = session.get("metadata", {}).get("plan", "pro")
            email = session.get("customer_details", {}).get("email")
            self._update_supabase(email, {"plan": plan, "stripe_customer_id": customer_id})

        elif event["type"] == "customer.subscription.deleted":
            customer_id = event["data"]["object"].get("customer")
            self._update_supabase_by_customer(customer_id, {"plan": "free"})

        self._json(200, {"received": True})

    def _update_supabase(self, email, data):
        if not email:
            return
        supabase_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
        service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not supabase_url or not service_key:
            return
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{supabase_url}/rest/v1/profiles?email=eq.{email}",
                data=json.dumps(data).encode(),
                method="PATCH",
                headers={"Content-Type": "application/json", "apikey": service_key, "Authorization": f"Bearer {service_key}", "Prefer": "return=minimal"},
            )
            urllib.request.urlopen(req)
        except Exception:
            pass

    def _update_supabase_by_customer(self, customer_id, data):
        if not customer_id:
            return
        supabase_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
        service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not supabase_url or not service_key:
            return
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{supabase_url}/rest/v1/profiles?stripe_customer_id=eq.{customer_id}",
                data=json.dumps(data).encode(),
                method="PATCH",
                headers={"Content-Type": "application/json", "apikey": service_key, "Authorization": f"Bearer {service_key}", "Prefer": "return=minimal"},
            )
            urllib.request.urlopen(req)
        except Exception:
            pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, Stripe-Signature")
        self.end_headers()

    def _json(self, status, data):
        body = json.dumps(data)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))
