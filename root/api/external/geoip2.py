
#!/usr/bin/env python3
""" Get GeoIP2 information for a given IP address. """
import geoip2.database
from config import cfg

def get_city(ip: str) -> dict[str, str]:
    """ Get GeoIP2 information for a given IP address. """
    geo_info: dict[str, str] = {
        'country': '',
        'state': '',
        'city': '',
        'zip': '',
        'latitude': '',
        'longitude': '',
        'iso_code': '',
        'ip': ip,
        'status': 'fail'
    }

    if not ip:
        geo_info['status'] = 'ip_empty'

    elif cfg.geo_city_db_exists is False:
        geo_info['status'] = 'db_missing'

    else:
        try:
            with geoip2.database.Reader(cfg.geo_city_db_path) as reader_db:
                data_city = reader_db.city(ip)

            if data_city is None:
                geo_info['status'] = 'no_data'
            else:
                geo_info['country'] = data_city.country.name or ""
                geo_info['state'] = data_city.subdivisions.most_specific.name or ""
                geo_info['city'] = data_city.city.name or ""
                geo_info['zip'] = data_city.postal.code or ""
                geo_info['latitude'] = str(data_city.location.latitude or "")
                geo_info['longitude'] = str(data_city.location.longitude or "")
                geo_info['iso_code'] = data_city.country.iso_code or ""
                geo_info['status'] = 'success'

        except geoip2.errors.AddressNotFoundError as e:
            geo_info['status'] = 'ip_not_found'
            geo_info['error_message'] = str(e)

        except ValueError as ve:
            geo_info['status'] = 'invalid_ip'
            geo_info['error_message'] = str(ve)

        except Exception as e: # pylint: disable=broad-except
            geo_info['status'] = 'exception'
            geo_info['error_message'] = str(e)
            print(f"Error fetching GeoIP2 data for IP {ip}: {e}", flush=True)

    if cfg.debug:
        print("[DEBUG] GeoIP city:", geo_info)
    return geo_info


def get_asn(ip: str) -> str:
    """ Get ASN information for a given IP address. """
    asn_info = ""
    if not ip:
        return asn_info

    if cfg.geo_asn_db_exists is False:
        return asn_info

    try:
        with geoip2.database.Reader(cfg.geo_asn_db_path) as reader_db:
            data_asn = reader_db.asn(ip)
            if data_asn is None:
                asn_info = "Missing ASN data"
                if cfg.debug:
                    print(f"[DEBUG] No ASN data for IP {ip} in ASN database", flush=True)

            else:
                asn_info = data_asn.autonomous_system_organization or ""

    except geoip2.errors.AddressNotFoundError as e:
        asn_info = "No ASN associated"
        if cfg.debug:
            print(f"[DEBUG] ASN not found for IP {ip}: {e}", flush=True)

    except ValueError as ve:
        asn_info = "Invalid IP address"
        if cfg.debug:
            print(f"[DEBUG] Invalid IP {ip}: {ve}", flush=True)

    except Exception as e: # pylint: disable=broad-except
        asn_info = f"An error occurred: {e}"
        print(f"Error fetching ASN data for IP {ip}: {e}", flush=True)

    return asn_info
