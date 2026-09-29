-- Reference data and the initial inventory, copied statement-for-statement from the monolith's
-- synthetic seed (ticketing/monolith/db/seed.sql) so ids (performanceId, seatInventoryId,
-- priceZoneId) are the same opaque identifiers on both sides of the demo.
-- Every name here is invented; no real company, person or venue.

INSERT INTO venues (code, name, city, timezone, capacity) VALUES
 ('TLM', 'Tallowmere Arena',   'Port Averly',  'UTC', 20000),
 ('OSH', 'Ossery Hall',        'Kestrelford',  'UTC', 2400),
 ('QFT', 'Quillfield Theater', 'Larkspur Bay', 'UTC', 1200);

-- Arena: 10 sections x 50 rows x 40 seats; Hall: 4 x 30 x 20; Theater: 3 x 20 x 20
INSERT INTO venue_sections (venue_id, code, name, row_count, seats_per_row)
SELECT 1, 'A' || lpad(g::text, 2, '0'), 'Arena Section ' || g, 50, 40 FROM generate_series(1, 10) g;
INSERT INTO venue_sections (venue_id, code, name, row_count, seats_per_row)
SELECT 2, 'H' || g, 'Hall Section ' || g, 30, 20 FROM generate_series(1, 4) g;
INSERT INTO venue_sections (venue_id, code, name, row_count, seats_per_row)
SELECT 3, 'T' || g, 'Theater Section ' || g, 20, 20 FROM generate_series(1, 3) g;

INSERT INTO price_zones (venue_id, code, name)
SELECT v.id, z.code, z.name FROM venues v
CROSS JOIN (VALUES ('P1', 'Premium'), ('P2', 'Standard'), ('P3', 'Value')) AS z(code, name);

-- seat -> price zone: first fifth of rows premium, next two fifths standard, rest value
INSERT INTO seats (section_id, price_zone_id, row_label, seat_number, accessible)
SELECT s.id,
       (SELECT pz.id FROM price_zones pz WHERE pz.venue_id = s.venue_id AND pz.code =
          CASE WHEN r <= s.row_count / 5 THEN 'P1' WHEN r <= (s.row_count * 3) / 5 THEN 'P2' ELSE 'P3' END),
       'R' || lpad(r::text, 2, '0'), n, (n <= 2 AND r = 1)
FROM venue_sections s
CROSS JOIN LATERAL generate_series(1, s.row_count) r
CROSS JOIN LATERAL generate_series(1, s.seats_per_row) n;

-- 3 performances per event, on the event's venue. The monolith derives the venue from the
-- event code (…ARENA -> 1, …HALL -> 2, else 3); the eight seeded events map as listed here.
INSERT INTO performances (event_id, venue_id, starts_at, doors_at, max_per_order)
SELECT e.id,
       e.venue_id,
       date_trunc('day', now()) + (e.id * 7 + k) * interval '1 day' + interval '20 hours',
       date_trunc('day', now()) + (e.id * 7 + k) * interval '1 day' + interval '19 hours',
       8
FROM (VALUES (1, 1), (2, 2), (3, 2), (4, 1), (5, 3), (6, 3), (7, 2), (8, 3)) AS e(id, venue_id)
CROSS JOIN generate_series(0, 2) k
ORDER BY e.id, k;

INSERT INTO seat_inventory (performance_id, seat_id, status)
SELECT p.id, s.id, 'AVAILABLE'
FROM performances p
JOIN venue_sections vs ON vs.venue_id = p.venue_id
JOIN seats s ON s.section_id = vs.id;
