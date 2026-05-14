#!/bin/bash
set -e

# Start all Legal Multi-Agent System services
# Registry must be first, then leaf agents, then orchestrators

if [ -x ".venv/bin/python" ]; then
    PYTHON_CMD=".venv/bin/python"
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
else
    echo "Error: neither 'python' nor 'python3' is available in PATH."
    exit 1
fi

echo "Starting Registry service on port 10000..."
"$PYTHON_CMD" -m registry &
REGISTRY_PID=$!
sleep 2

echo "Starting Tax Agent on port 10102..."
"$PYTHON_CMD" -m tax_agent &
TAX_PID=$!

echo "Starting Compliance Agent on port 10103..."
"$PYTHON_CMD" -m compliance_agent &
COMPLIANCE_PID=$!
sleep 3

echo "Starting Law Agent on port 10101..."
"$PYTHON_CMD" -m law_agent &
LAW_PID=$!
sleep 3

echo "Starting Customer Agent on port 10100..."
"$PYTHON_CMD" -m customer_agent &
CUSTOMER_PID=$!
sleep 1

for pid in $REGISTRY_PID $TAX_PID $COMPLIANCE_PID $LAW_PID $CUSTOMER_PID; do
    if ! kill -0 "$pid" 2>/dev/null; then
        echo "Error: one or more services failed to start. Check logs above."
        exit 1
    fi
done

echo ""
echo "All services started:"
echo "  Registry:         http://localhost:10000"
echo "  Customer Agent:   http://localhost:10100"
echo "  Law Agent:        http://localhost:10101"
echo "  Tax Agent:        http://localhost:10102"
echo "  Compliance Agent: http://localhost:10103"
echo ""
echo "Run test_client.py to send a query:"
echo "  $PYTHON_CMD test_client.py"
echo ""
echo "Press Ctrl+C to stop all services."

# Stop all services on Ctrl+C
trap "echo ''; echo 'Stopping all services...'; kill $REGISTRY_PID $TAX_PID $COMPLIANCE_PID $LAW_PID $CUSTOMER_PID 2>/dev/null; exit" INT

# Wait for all background processes
wait $REGISTRY_PID $TAX_PID $COMPLIANCE_PID $LAW_PID $CUSTOMER_PID
