import { sqliteTable, text, integer } from 'drizzle-orm/sqlite-core';
// Only request counts live at the edge; user profiles and findings stay in AWS.
export const requestQuota = sqliteTable('request_quota', {
  key: text('key').primaryKey(),
  period: text('period').notNull(),
  used: integer('used').notNull(),
});
export const authSession = sqliteTable('auth_session', {
  hash: text('hash').primaryKey(), account: text('account').notNull(),
  email: text('email').notNull(), expires: integer('expires').notNull(),
});
export const agentConnection = sqliteTable('agent_connection', {
  hash: text('hash').primaryKey(), account: text('account').notNull(),
  systemId: text('system_id').notNull(), expires: integer('expires').notNull(),
  lastSync: integer('last_sync').notNull(),
});
export const feedback = sqliteTable('feedback', {
  id: text('id').primaryKey(), account: text('account'), email: text('email'),
  kind: text('kind').notNull(), message: text('message').notNull(), page: text('page'),
  createdAt: integer('created_at').notNull(),
});
