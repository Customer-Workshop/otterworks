-- Synthetic seed. Every name here is invented; no real company, person or venue.
-- Deterministic: re-running after db/reset.sql yields the same ids.

INSERT INTO promoters (code, name, commission_bp, payout_iban) VALUES
 ('PRM-PEL', 'Pellucid Promotions', 1000, 'XX00SYNTH0000000001'),
 ('PRM-QST', 'Quarrystone Live',    1200, 'XX00SYNTH0000000002'),
 ('PRM-BRW', 'Brambleway Presents',  900, 'XX00SYNTH0000000003');

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

INSERT INTO performers (name, genre) VALUES
 ('Static Meridian',            'Rock'),
 ('The Glass Orchards',         'Indie'),
 ('Hollow Pines Ensemble',      'Folk'),
 ('Velvet Cartography',         'Electronic'),
 ('Brass Lantern Collective',   'Jazz'),
 ('Quiet Engine Theatre Co.',   'Theatre');

INSERT INTO events (code, title, category, promoter_id, description, on_sale_at, status) VALUES
 ('EVT-SM-ARENA', 'Static Meridian: The Long Signal Tour', 'CONCERT', 1, 'Arena tour, headline on-sale.', now() - interval '1 hour', 'ON_SALE'),
 ('EVT-GO-HALL',  'The Glass Orchards Live',                'CONCERT', 2, 'Two nights at the hall.',       now() - interval '10 days', 'ON_SALE'),
 ('EVT-HP-HALL',  'Hollow Pines Ensemble: Winter Songs',    'CONCERT', 3, 'Seated folk evening.',          now() - interval '20 days', 'ON_SALE'),
 ('EVT-VC-ARENA', 'Velvet Cartography: Night Maps',         'CONCERT', 1, 'Late show, arena floor.',       now() - interval '5 days', 'ON_SALE'),
 ('EVT-BL-THTR',  'Brass Lantern Collective Sessions',      'CONCERT', 2, 'Jazz residency.',               now() - interval '30 days', 'ON_SALE'),
 ('EVT-QE-THTR',  'Quiet Engine: A Play in Two Acts',       'THEATRE', 3, 'New writing season.',           now() - interval '15 days', 'ON_SALE'),
 ('EVT-SM-HALL',  'Static Meridian: Acoustic Hall Night',   'CONCERT', 1, 'Intimate acoustic set.',        now() - interval '2 days', 'ON_SALE'),
 ('EVT-GO-THTR',  'The Glass Orchards: Songs and Stories',  'CONCERT', 2, 'Seated storytelling show.',     now() - interval '8 days', 'ON_SALE');

INSERT INTO event_performers (event_id, performer_id, billing_order) VALUES
 (1,1,1),(2,2,1),(3,3,1),(4,4,1),(5,5,1),(6,6,1),(7,1,1),(8,2,1),(1,4,2);

-- 3 performances per event, on the event's venue
INSERT INTO performances (event_id, venue_id, starts_at, doors_at, max_per_order)
SELECT e.id,
       CASE WHEN e.code LIKE '%ARENA' THEN 1 WHEN e.code LIKE '%HALL' THEN 2 ELSE 3 END,
       date_trunc('day', now()) + (e.id * 7 + k) * interval '1 day' + interval '20 hours',
       date_trunc('day', now()) + (e.id * 7 + k) * interval '1 day' + interval '19 hours',
       8
FROM events e CROSS JOIN generate_series(0, 2) k
ORDER BY e.id, k;

INSERT INTO performance_price_levels (performance_id, price_zone_id, face_value_cents, demand_factor_bp)
SELECT p.id, pz.id,
       CASE pz.code WHEN 'P1' THEN 18900 WHEN 'P2' THEN 11900 ELSE 6900 END,
       10000
FROM performances p JOIN price_zones pz ON pz.venue_id = p.venue_id;

INSERT INTO seat_inventory (performance_id, seat_id, status)
SELECT p.id, s.id, 'AVAILABLE'
FROM performances p
JOIN venue_sections vs ON vs.venue_id = p.venue_id
JOIN seats s ON s.section_id = vs.id;

INSERT INTO delivery_methods (code, name, fee_cents) VALUES
 ('MOBILE', 'Mobile ticket', 0), ('PRINT', 'Print at home', 150), ('WILLCALL', 'Will call', 300);

INSERT INTO promo_codes (code, percent_off, event_id, max_uses, valid_until) VALUES
 ('FANCLUB10', 10, 1, 100000, now() + interval '90 days'),
 ('HALLNIGHT', 15, 2, 500,    now() + interval '30 days');

INSERT INTO customers (email, full_name, phone, marketing_opt_in)
SELECT 'fan' || lpad(g::text, 5, '0') || '@example.test', 'Synthetic Fan ' || g, '+1-555-01' || lpad((g % 100)::text, 2, '0'), (g % 3 = 0)
FROM generate_series(1, 5000) g;

INSERT INTO customer_addresses (customer_id, line1, city, postal_code)
SELECT id, (id % 900 + 100) || ' Example Street', 'Port Averly', lpad((id % 99999)::text, 5, '0') FROM customers;

INSERT INTO audit_log (module, action, entity_ref, detail) VALUES ('seed', 'SEEDED', 'boxoffice', 'synthetic seed loaded');
