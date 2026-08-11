from unittest.mock import Mock

import pytest
import requests

from app.services.rebrickable import RebrickableAPIError, RebrickableService


def response(status=200, payload=None):
    result = Mock()
    result.status_code = status
    result.ok = 200 <= status < 300
    result.json.return_value = payload
    return result


def test_service_successful_set_detail():
    session = Mock()
    session.get.return_value = response(
        payload={"set_num": "10300-1", "name": "Back to the Future Time Machine"}
    )
    service = RebrickableService("api-key", "user-token", session=session)

    result = service.get_set_details("10300-1")

    assert result["set_num"] == "10300-1"
    request_args = session.get.call_args
    assert request_args.args[0].endswith("/lego/sets/10300-1/")
    assert request_args.kwargs["headers"] == {"Authorization": "key api-key"}


def test_service_follows_set_list_pagination():
    session = Mock()
    session.get.side_effect = [
        response(payload={"count": 2, "next": "next-url", "results": [{"id": 1}]}),
        response(payload={"count": 2, "next": None, "results": [{"id": 2}]}),
    ]
    service = RebrickableService("api-key", "token", session=session)

    result = service.get_user_set_lists()

    assert [item["id"] for item in result["results"]] == [1, 2]
    assert session.get.call_count == 2


def test_service_api_error_is_safe():
    session = Mock()
    session.get.return_value = response(status=401, payload={"detail": "Invalid key"})
    service = RebrickableService("bad-key", "token", session=session)

    with pytest.raises(RebrickableAPIError, match="abgelehnt"):
        service.get_user_set_lists()


def test_service_timeout_is_safe():
    session = Mock()
    session.get.side_effect = requests.Timeout("secret request details")
    service = RebrickableService("api-key", "token", session=session)

    with pytest.raises(RebrickableAPIError, match="zu lange gedauert"):
        service.get_user_set_lists()


def test_service_generates_user_token_without_retaining_password():
    session = Mock()
    session.post.return_value = response(status=201, payload={"user_token": "new-token"})
    service = RebrickableService("api-key", session=session)

    token = service.generate_user_token("brickfan", "one-time-password")

    assert token == "new-token"
    call = session.post.call_args
    assert call.args[0].endswith("/users/_token/")
    assert call.kwargs["data"]["username"] == "brickfan"


def test_service_loads_inventory_with_part_images():
    session = Mock()
    session.get.return_value = response(
        payload={
            "count": 1,
            "next": None,
            "results": [
                {
                    "id": 7,
                    "quantity": 4,
                    "part": {
                        "part_num": "3001",
                        "name": "Brick 2 x 4",
                        "part_img_url": "https://cdn.rebrickable.com/part.jpg",
                    },
                    "color": {"id": 4, "name": "Red"},
                }
            ],
        }
    )
    service = RebrickableService("api-key", session=session)

    parts = service.get_set_parts("10300-1")

    assert parts[0]["part"]["part_img_url"].endswith("part.jpg")
    assert session.get.call_args.kwargs["params"]["inc_part_details"] == 1


def test_service_searches_all_user_sets():
    session = Mock()
    session.get.return_value = response(
        payload={"count": 1, "results": [{"list_id": 3, "set": {"name": "Emerald Night"}}]}
    )
    service = RebrickableService("api-key", "user-token", session=session)

    result = service.search_user_sets("Emerald", page=2)

    assert result["count"] == 1
    params = session.get.call_args.kwargs["params"]
    assert params["search"] == "Emerald"
    assert params["page"] == 2
