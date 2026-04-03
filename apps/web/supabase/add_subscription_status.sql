-- SAAS-01: Add subscription_status column to profiles table
-- Required by Stripe webhook handler (updateUserPlan) and dashboard UI
ALTER TABLE public.profiles
  ADD COLUMN IF NOT EXISTS subscription_status text DEFAULT 'active'
  CHECK (subscription_status IN ('active', 'past_due', 'canceled', 'trialing'));
