import { sqliteTable, text, integer } from 'drizzle-orm/sqlite-core';
// Only request counts live at the edge; user profiles and findings stay in AWS.
export const requestQuota = sqliteTable('request_quota', {
  key: text('key').primaryKey(),
  period: text('period').notNull(),
  used: integer('used').notNull(),
});
