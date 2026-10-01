from __future__ import annotations

import json

import httpx

from app.providers.amazon_creators import AmazonCreatorsClient

IMG = "https://m.media-amazon.com/images/I/41cNJGm9ZFL._SL500_.jpg"


class _Amazon:
    def __init__(self, *, eligible: bool = True, images: dict[str, str] | None = None) -> None:
        self.eligible = eligible
        self.images = images or {}
        self.token_calls = 0
        self.item_calls: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.amazon.com":
            self.token_calls += 1
            body = json.loads(request.content)
            assert body["grant_type"] == "client_credentials"
            assert body["scope"] == "creatorsapi::default"
            return httpx.Response(200, json={"access_token": "Atc|t", "expires_in": 3600})
        payload = json.loads(request.content)
        self.item_calls.append(payload)
        assert request.headers["x-marketplace"] == "www.amazon.ca"
        assert request.headers["Authorization"] == "Bearer Atc|t"
        if not self.eligible:
            return httpx.Response(403, json={"errors": [{"code": "AssociateNotEligible"}]})
        items = [
            {"asin": a, "images": {"primary": {"large": {"url": self.images[a]}}}}
            for a in payload["itemIds"]
            if a in self.images
        ]
        return httpx.Response(200, json={"itemsResult": {"items": items}})


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def _client(fake: _Amazon, clock: _Clock) -> AmazonCreatorsClient:
    return AmazonCreatorsClient(
        "id",
        "secret",
        partner_tag="saveiq-20",
        transport=httpx.MockTransport(fake.handler),
        clock=clock,
        sleep=clock.sleep,
    )


def test_fetches_in_batches_of_ten_and_caches() -> None:
    asins = [f"B0000000{i:02d}" for i in range(12)]
    fake = _Amazon(images={a: IMG for a in asins})
    clock = _Clock()
    client = _client(fake, clock)

    assert client.cached(asins) == {}
    client.warm(asins)
    assert [len(c["itemIds"]) for c in fake.item_calls] == [10, 2]
    call = fake.item_calls[0]
    assert call["partnerTag"] == "saveiq-20"
    assert call["marketplace"] == "www.amazon.ca"
    assert call["resources"] == ["images.primary.large"]
    assert client.cached(asins) == {a: IMG for a in asins}
    assert fake.token_calls == 1
    assert clock.slept and min(clock.slept) > 1.0  # never faster than 1 request/second

    client.warm(asins)  # everything cached: no further calls
    assert len(fake.item_calls) == 2


def test_not_eligible_backs_off_instead_of_hammering_amazon() -> None:
    fake = _Amazon(eligible=False)
    clock = _Clock()
    client = _client(fake, clock)

    assert client.image_for("B004VBC0FM") is None
    assert client.image_for("B0052EH8OA") is None
    assert len(fake.item_calls) == 1  # the second lookup never left the building

    clock.now += 3601
    fake.eligible = True
    fake.images = {"B004VBC0FM": IMG}
    assert client.image_for("B004VBC0FM") == IMG


def test_only_amazon_cdn_urls_are_kept_and_misses_are_remembered() -> None:
    fake = _Amazon(images={"B000000001": "https://evil.example/x.jpg", "B000000002": IMG})
    clock = _Clock()
    client = _client(fake, clock)

    client.warm(["B000000001", "B000000002", "B000000003"])
    assert client.cached(["B000000001", "B000000002", "B000000003"]) == {"B000000002": IMG}
    assert client.missing(["B000000001", "B000000003"]) == []  # not asked again for hours
