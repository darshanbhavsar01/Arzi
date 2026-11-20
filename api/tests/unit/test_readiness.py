from arzi.services.readiness import CheckState, check_readiness
from tests.fakes import FakeProbe


async def test_no_probes_means_ready() -> None:
    report = await check_readiness([], timeout_s=1)

    assert report.ready is True
    assert report.checks == ()


async def test_results_keep_probe_order_and_all_must_pass() -> None:
    probes = [FakeProbe("slow", delay_s=0.05), FakeProbe("broken", error=ValueError("x"))]

    report = await check_readiness(probes, timeout_s=1)

    assert report.ready is False
    assert [(c.name, c.state, c.detail) for c in report.checks] == [
        ("slow", CheckState.OK, None),
        ("broken", CheckState.FAILED, "ValueError"),
    ]


async def test_hung_probe_times_out_without_blocking_others() -> None:
    probes = [FakeProbe("hung", delay_s=5), FakeProbe("fine")]

    report = await check_readiness(probes, timeout_s=0.05)

    hung, fine = report.checks
    assert (hung.state, hung.detail) == (CheckState.FAILED, "timeout")
    assert hung.latency_ms < 1000
    assert fine.state is CheckState.OK
