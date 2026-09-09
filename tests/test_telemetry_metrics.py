import subprocess
import sys
import textwrap

# The global MeterProvider can only be set once per process, so run in a subprocess.
_SCRIPT = textwrap.dedent(
    """
    from opentelemetry import metrics
    from opentelemetry.sdk.metrics.view import (
        ExplicitBucketHistogramAggregation,
        View,
    )
    from prometheus_client import generate_latest

    from aidial_sdk.telemetry.init import init_telemetry
    from aidial_sdk.telemetry.types import MetricsConfig, TelemetryConfig

    init_telemetry(
        None,
        TelemetryConfig(
            metrics=MetricsConfig(
                prometheus_export=True,
                port=0,  # ephemeral: metrics are read from the registry below
                meter_provider_views=[
                    View(
                        instrument_name="http.server.duration",
                        aggregation=ExplicitBucketHistogramAggregation(
                            (100, 500)
                        ),
                    )
                ],
            )
        ),
    )

    metrics.get_meter("test").create_histogram(
        "http.server.duration", unit="ms"
    ).record(300)

    print(generate_latest().decode())
    """
)


def test_metrics_views_override_histogram_buckets():
    out = subprocess.run(  # noqa: S603
        [sys.executable, "-c", _SCRIPT], capture_output=True, text=True
    ).stdout

    buckets = [
        line
        for line in out.splitlines()
        if line.startswith("http_server_duration_milliseconds_bucket")
    ]
    boundaries = [line.split('le="')[1].split('"')[0] for line in buckets]

    assert boundaries == ["100", "500", "+Inf"], out
    # The recorded 300ms lands in the (100, 500] bucket.
    assert [line.rsplit(" ", 1)[1] for line in buckets] == ["0.0", "1.0", "1.0"]
