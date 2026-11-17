# Deliverable: 04-door

This is the definition of done for the maker. It says what good looks like.
It does not say how the work is tested. Keep tests out of this file.

## Hand in

`door.md`.

## Format

1. **Release**: the door's name, version or tag, and how its checksum or signature was verified.
2. **Folders**: where the door, its live manifest and its state live.
3. **Service**: the service name, how to stop it, start it and see its log; who said yes to installing it.
4. **Addresses**: the loopback URL; the https route URL if any; the door's host list.
5. **Requirements**: each item of "What the door must do" in `door-placement.md`, marked met or not.
6. **Doctor**: one row per connection: present or missing, reachable or not. No values.
7. **Slowest call**: the door's slowest expected call in seconds.

## Must be true

- The door listens on loopback only. Any route is private (tailnet-only), never public.
- The route's host is in the door's host list exactly.
- Every OAuth sign-in was done by the person.
- Every connection the plan marked for connecting has a doctor row.
- No value appears anywhere.

## Out of scope

- Editing any harness config. That is `05x`.
