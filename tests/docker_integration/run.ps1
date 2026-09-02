echo "=== Starting 2-Container Docker Integration Test ==="

# Create docker network if not exists
$nets = docker network ls --format "{{.Name}}"
if ($nets -notmatch "pardus_net") {
    echo "Creating pardus_net docker network..."
    docker network create pardus_net
}

# Create shared volume folder on host
$SharedDir = "$pwd\tests\docker_integration\shared"
if (-not (Test-Path $SharedDir)) {
    New-Item -ItemType Directory -Path $SharedDir | Out-Null
}

echo "Starting Alice (Server) in background..."
$AliceCmd = "docker run --rm -d --name pardus-alice --network pardus_net -v `"${pwd}:/app`" -v `"${SharedDir}:/shared`" --entrypoint=python3 pardus-test /app/tests/docker_integration/alice.py"
Invoke-Expression $AliceCmd | Out-Null

echo "Starting Bob (Client) in foreground..."
$BobCmd = "docker run --rm --name pardus-bob --network pardus_net -v `"${pwd}:/app`" -v `"${SharedDir}:/shared`" --entrypoint=python3 pardus-test /app/tests/docker_integration/bob.py"
Invoke-Expression $BobCmd

# Clean up Alice
echo "Stopping Alice..."
docker stop pardus-alice | Out-Null

echo "Integration test completed!"
