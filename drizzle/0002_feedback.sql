CREATE TABLE `feedback` (
	`id` text PRIMARY KEY NOT NULL,
	`account` text,
	`email` text,
	`kind` text NOT NULL,
	`message` text NOT NULL,
	`page` text,
	`created_at` integer NOT NULL
);
--> statement-breakpoint
CREATE INDEX `idx_feedback_created_at` ON `feedback` (`created_at` DESC);
