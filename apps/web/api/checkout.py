"""Stripe Checkout session creation.

POST /api/checkout -> { url }
Body: { plan: "pro" | "business" }

Requires env vars:
  STRIPE_SECRET_KEY
  STRIPE_PRO_PRICE_ID
  STRIPE_BUSINESS_PRICE_ID
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
        try:
            import stripe
        except ImportError:
            self._json_response(500, {"error": "stripe package not installed"})
            return

        stripe_key = os.environ.get("STRIPE_SECRET_KEY")
        if not stripe_key:
            self._json_response(500, {"error": "STRIPE_SECRET_KEY not configured"})
            return

        stripe.api_key = stripe_key

        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length)) if content_length > 0 else {}
        except (json.JSONDecodeError, ValueError):
            self._json_response(400, {"error": "Invalid JSON body"})
            return

        plan = body.get("plan", "")
        if plan not in ("pro", "business"):
            self._json_response(400, {"error": "Invalid plan. Must be 'pro' or 'business'"})
            return

        price_id = PRICE_IDS.get(plan)
        if not price_id:
            self._json_response(500, {"error": f"Price ID not configured for plan: {plan}"})
            return

        # Extract origin for success/cancel URLs
        origin = self.headers.get("Origin", "https://faultray.com")

        try:
            session = stripe.checkout.Session.create(
                mode="subscription",
                line_items=[{"price": price_id, "quantity": 1}],
                success_url=f"{origin}/dashboard?checkout=success&plan={plan}",
                cancel_url=f"{origin}/pricing?checkout=cancelled",
                metadata={"plan": plan},
            )
            self._json_response(200, {"url": session.url})
        except stripe.StripeError as e:
            self._json_response(400, {"error": str(e)})
        except Exception as e:
            self._json_response(500, {"error": str(e)})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def _json_response(self, status, data):
        body = json.dumps(data)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))
