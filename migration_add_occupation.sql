-- Run this once in Supabase SQL Editor before deploying the updated bot.
alter table students add column if not exists occupation text;
