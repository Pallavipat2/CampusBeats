import os

from dotenv import load_dotenv

try:
    from supabase import create_client
except ImportError:
    create_client = None


load_dotenv()

_supabase_client = None


def _require_supabase():
    if create_client is None:
        raise ImportError(
            "supabase is required for this project. Install the `supabase` package first."
        )


def get_supabase_client():
    global _supabase_client

    if _supabase_client is not None:
        return _supabase_client

    _require_supabase()

    url = os.getenv("DBURL")
    key = os.getenv("DBKEY")

    if not url or not key:
        raise ValueError("DBURL and DBKEY must be set in the environment.")

    _supabase_client = create_client(url, key)
    return _supabase_client


def result_data(response):
    data = getattr(response, "data", None)
    return data or []


def first_row(response):
    data = result_data(response)
    return data[0] if data else None
