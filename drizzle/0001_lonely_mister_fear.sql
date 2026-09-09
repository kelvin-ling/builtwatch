CREATE TABLE `agent_connection` (
	`hash` text PRIMARY KEY NOT NULL,
	`account` text NOT NULL,
	`system_id` text NOT NULL,
	`expires` integer NOT NULL,
	`last_sync` integer NOT NULL
);
--> statement-breakpoint
CREATE TABLE `auth_session` (
	`hash` text PRIMARY KEY NOT NULL,
	`account` text NOT NULL,
	`email` text NOT NULL,
	`expires` integer NOT NULL
);
