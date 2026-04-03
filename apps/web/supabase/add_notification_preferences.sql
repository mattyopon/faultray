-- RETAIN-02: Add notification_preferences JSONB column to profiles
-- Stores email notification settings per user
ALTER TABLE public.profiles
  ADD COLUMN IF NOT EXISTS notification_preferences jsonb DEFAULT '{
    "simulationCompleted": true,
    "scoreDegradation": true,
    "weeklySummary": false,
    "monthlyReport": false,
    "criticalAlertImmediate": true
  }'::jsonb;
