"""
async moodle api client — wraps the moodle web services REST api.

all calls hit: {MOODLE_URL}/webservice/rest/server.php
file downloads go through: {MOODLE_URL}/webservice/pluginfile.php

api docs: https://docs.moodle.org/dev/Web_service_API_functions
"""
import logging
from pathlib import Path
from typing import Any

import httpx

from config import settings

logger = logging.getLogger(__name__)

# standard moodle endpoints
_API_URL  = f"{settings.moodle_url}/webservice/rest/server.php"
_FILE_URL = f"{settings.moodle_url}/webservice/pluginfile.php"
_TIMEOUT  = httpx.Timeout(60.0)


def _flatten_params(params: dict) -> dict:
    """
    moodle doesn't accept python lists directly.
    converts them to indexed format: courseids=[1,2] → courseids[0]=1, courseids[1]=2
    """
    flat: dict = {}
    for key, val in params.items():
        if isinstance(val, list):
            for i, item in enumerate(val):
                flat[f"{key}[{i}]"] = item
        else:
            flat[key] = val
    return flat


async def _call(function: str, **params: Any) -> Any:
    """
    generic call to moodle web services. returns parsed json.

    args:
        function: the ws function name, e.g. 'core_course_get_contents'
        **params: query string params
    """
    raw = {
        "wstoken": settings.moodle_token,
        "wsfunction": function,
        "moodlewsrestformat": "json",
        **params,
    }
    payload = _flatten_params(raw)
    async with httpx.AsyncClient(timeout=_TIMEOUT, verify=False) as client:
        resp = await client.post(_API_URL, data=payload)
        resp.raise_for_status()
        data = resp.json()

    # moodle returns {"exception": ..., "message": ...} on errors
    if isinstance(data, dict) and "exception" in data:
        raise RuntimeError(
            f"Moodle API error [{function}]: {data.get('message', data)}"
        )
    return data


# api functions we actually use

async def get_course_contents(course_id: int) -> list[dict]:
    """
    core_course_get_contents — gets all sections and modules for a course
    (files, pages, urls, folders etc.)

    used during indexing to find all available course materials.
    response: list of sections, each with a modules[] list.
    """
    return await _call("core_course_get_contents", courseid=course_id)


async def get_course_by_id(course_id: int) -> dict:
    """
    core_course_get_courses_by_field — gets course details (name, shortname,
    summary etc.) by id.

    used to check the course exists and grab its metadata.
    """
    result = await _call(
        "core_course_get_courses_by_field",
        field="id",
        value=course_id,
    )
    courses = result.get("courses", [])
    if not courses:
        raise ValueError(f"course with id {course_id} not found in moodle.")
    return courses[0]


async def get_pages_by_course(course_id: int) -> list[dict]:
    """
    mod_page_get_pages_by_courses — returns html content of 'page' type
    modules in a course.

    used to extract text from inline pages (not separate files).
    relevant field: pages[].content (html string)
    """
    result = await _call(
        "mod_page_get_pages_by_courses",
        courseids=[course_id],
    )
    return result.get("pages", [])


async def get_resources_by_course(course_id: int) -> list[dict]:
    """
    mod_resource_get_resources_by_courses — returns list of file resources
    attached to a course.

    used to map module id → filename, sometimes needed when
    core_course_get_contents doesn't include the file preview.
    """
    result = await _call(
        "mod_resource_get_resources_by_courses",
        courseids=[course_id],
    )
    return result.get("resources", [])


async def download_file(file_url: str, dest_path: Path) -> Path:
    """
    downloads a course file via pluginfile.php.

    moodle needs the token in the query string for restricted files.
    file_url comes from core_course_get_contents → contents[].fileurl

    args:
        file_url: moodle file url (may or may not already have token)
        dest_path: local path to save the temp file
    returns the path of the downloaded file.
    """
    # append token if it's not already in the url
    sep = "&" if "?" in file_url else "?"
    url_with_token = f"{file_url}{sep}token={settings.moodle_token}"

    dest_path.parent.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=_TIMEOUT, verify=False, follow_redirects=True) as client:
        async with client.stream("GET", url_with_token) as resp:
            resp.raise_for_status()
            with open(dest_path, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=8192):
                    f.write(chunk)

    logger.debug(f"downloaded: {dest_path.name} ({dest_path.stat().st_size} bytes)")
    return dest_path
