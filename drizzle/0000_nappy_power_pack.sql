CREATE TABLE `request_quota` (
	`key` text PRIMARY KEY NOT NULL,
	`period` text NOT NULL,
	`used` integer NOT NULL
);
