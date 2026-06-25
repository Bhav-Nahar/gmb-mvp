"""Regression tests for GBPLocationMapper address decomposition.

Guards the bug where city/state/country/postal_code were populated by the mapper
but not declared on LocationModel, so Pydantic silently dropped them and the
sync task later crashed with AttributeError on p_loc.city.
"""
from app.providers.gbp.mapper import GBPLocationMapper
from app.providers.gbp.schemas import GBPLocationRaw


def _raw(**addr):
    return GBPLocationRaw(
        name="locations/1",
        title="Test Location",
        storefrontAddress=addr or None,
    )


def test_mapper_decomposes_structured_address():
    m = GBPLocationMapper.to_model(_raw(
        addressLines=["123 St"], locality="Pune",
        administrativeArea="MH", postalCode="411001", regionCode="IN",
    ))
    assert m.city == "Pune"
    assert m.state == "MH"
    assert m.country == "IN"
    assert m.postal_code == "411001"
    # address is preserved as the combined JSON string, not dropped
    assert m.address and "Pune" in m.address


def test_mapper_address_fields_are_attributes_not_dropped():
    # The actual failure mode: accessing the attribute must not raise, even when
    # the address has no locality. Defaults to None, never AttributeError.
    m = GBPLocationMapper.to_model(_raw(addressLines=["123 St"]))
    assert m.city is None
    assert m.state is None
    assert m.country is None
    assert m.postal_code is None


def test_mapper_handles_missing_address():
    m = GBPLocationMapper.to_model(_raw())
    assert m.city is None
    assert m.address is None
