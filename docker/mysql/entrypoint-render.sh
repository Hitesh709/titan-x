#!/bin/bash
set -euo pipefail

# Render keeps /var/lib/mysql on a persistent disk. The official MySQL image
# only applies MYSQL_* credentials during first initialization. If the
# persistent database was initialized with an older password, synchronize the
# application account before normal startup without deleting any data.

DATADIR="${MYSQL_DATADIR:-/var/lib/mysql}"
SOCKET="/tmp/mysql-render-recovery.sock"
RECOVERY_PID=""

cleanup_recovery() {
  if [[ -n "${RECOVERY_PID}" ]]; then
    kill "${RECOVERY_PID}" >/dev/null 2>&1 || true
    wait "${RECOVERY_PID}" >/dev/null 2>&1 || true
  fi
  rm -f "${SOCKET}" "${SOCKET}-lock" /tmp/mysql-render-recovery.pid
}

trap cleanup_recovery EXIT

# A persistent MySQL 8 datadir contains mysql.ibd. Do not delete or recreate
# the datadir: it contains the application's existing database data.
if [[ -n "${MYSQL_PASSWORD:-}" && -f "${DATADIR}/mysql.ibd" ]]; then
  echo "[Render MySQL] Existing data directory detected; synchronizing titan_x credentials."

  mysqld \
    --datadir="${DATADIR}" \
    --skip-grant-tables \
    --skip-networking \
    --socket="${SOCKET}" \
    --pid-file=/tmp/mysql-render-recovery.pid \
    >/tmp/mysql-render-recovery.log 2>&1 &
  RECOVERY_PID=$!

  ready=0
  for _ in $(seq 1 60); do
    if [[ -S "${SOCKET}" ]] && mysql --no-defaults --protocol=socket --socket="${SOCKET}" -uroot -e "SELECT 1" >/dev/null 2>&1; then
      ready=1
      break
    fi
    sleep 1
  done

  if [[ "${ready}" != "1" ]]; then
    echo "[Render MySQL] Recovery server did not become ready." >&2
    cat /tmp/mysql-render-recovery.log >&2 || true
    exit 1
  fi

  escaped_password="${MYSQL_PASSWORD//\\/\\\\}"
  escaped_password="${escaped_password//'/''}"

  mysql --no-defaults --protocol=socket --socket="${SOCKET}" -uroot <<SQL
FLUSH PRIVILEGES;
CREATE USER IF NOT EXISTS 'titan_x'@'%' IDENTIFIED BY '${escaped_password}';
ALTER USER 'titan_x'@'%' IDENTIFIED BY '${escaped_password}';
GRANT ALL PRIVILEGES ON titan_x.* TO 'titan_x'@'%';
FLUSH PRIVILEGES;
SQL

  echo "[Render MySQL] titan_x password synchronized successfully."
fi

trap - EXIT
cleanup_recovery
exec /usr/local/bin/docker-entrypoint.sh "$@"
