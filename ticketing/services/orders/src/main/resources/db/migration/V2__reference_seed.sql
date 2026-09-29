-- Synthetic reference seed, copied verbatim (same statements, same order, same ids) from the monolith's
-- db/seed.sql so performanceId / priceZoneId are the same opaque identifiers in every service.
-- Every name here is invented; no real company, person or venue.

INSERT INTO venues (code, name, city, timezone, capacity) VALUES
 ('TLM', 'Tallowmere Arena',   'Port Averly',  'UTC', 20000),
 ('OSH', 'Ossery Hall',        'Kestrelford',  'UTC', 2400),
 ('QFT', 'Quillfield Theater', 'Larkspur Bay', 'UTC', 1200);

INSERT INTO price_zones (venue_id, code, name)
SELECT v.id, z.code, z.name FROM venues v
CROSS JOIN (VALUES ('P1', 'Premium'), ('P2', 'Standard'), ('P3', 'Value')) AS z(code, name);

INSERT INTO events (code, title, category, promoter_id, description, on_sale_at, status) VALUES
 ('EVT-SM-ARENA', 'Static Meridian: The Long Signal Tour', 'CONCERT', 1, 'Arena tour, headline on-sale.', now() - interval '1 hour', 'ON_SALE'),
 ('EVT-GO-HALL',  'The Glass Orchards Live',                'CONCERT', 2, 'Two nights at the hall.',       now() - interval '10 days', 'ON_SALE'),
 ('EVT-HP-HALL',  'Hollow Pines Ensemble: Winter Songs',    'CONCERT', 3, 'Seated folk evening.',          now() - interval '20 days', 'ON_SALE'),
 ('EVT-VC-ARENA', 'Velvet Cartography: Night Maps',         'CONCERT', 1, 'Late show, arena floor.',       now() - interval '5 days', 'ON_SALE'),
 ('EVT-BL-THTR',  'Brass Lantern Collective Sessions',      'CONCERT', 2, 'Jazz residency.',               now() - interval '30 days', 'ON_SALE'),
 ('EVT-QE-THTR',  'Quiet Engine: A Play in Two Acts',       'THEATRE', 3, 'New writing season.',           now() - interval '15 days', 'ON_SALE'),
 ('EVT-SM-HALL',  'Static Meridian: Acoustic Hall Night',   'CONCERT', 1, 'Intimate acoustic set.',        now() - interval '2 days', 'ON_SALE'),
 ('EVT-GO-THTR',  'The Glass Orchards: Songs and Stories',  'CONCERT', 2, 'Seated storytelling show.',     now() - interval '8 days', 'ON_SALE');

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

INSERT INTO delivery_methods (code, name, fee_cents) VALUES
 ('MOBILE', 'Mobile ticket', 0), ('PRINT', 'Print at home', 150), ('WILLCALL', 'Will call', 300);

INSERT INTO promo_codes (code, percent_off, event_id, max_uses, valid_until) VALUES
 ('FANCLUB10', 10, 1, 100000, now() + interval '90 days'),
 ('HALLNIGHT', 15, 2, 500,    now() + interval '30 days');
