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
  if [[ -n "${RECOVERY_PID}" ]] && kill -0 "${RECOVERY_PID}" 2>/dev/null; then
    mysqladmin --no-defaults --socket="${SOCKET}" -uroot shutdown >/dev/null 2>&1 || true
    kill "${RECOVERY_PID}" >/dev/null 2>&1 || true
    wait "${RECOVERY_PID}" >/dev/null 2>&1 || true
  fi
  rm -f "${SOCKET}" "${SOCKET}-lock" /tmp/mysql-render-recovery.pid
}

trap cleanup_recovery EXIT

# MySQL 8 does not reliably expose the old mysql/user.ibd path. The presence
# of mysql.ibd indicates an initialized MySQL 8 data dictionary on the
# persistent Render disk.
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
    if mysqladmin --no-defaults --socket="${SOCKET}" ping >/dev/null 2>&1; then
      ready=1
      break
    fi
    if ! kill -0 "${RECOVERY_PID}" 2>/dev/null; then
      echo "[Render MySQL] Recovery server failed to start." >&2
      cat /tmp/mysql-render-recovery.log >&2 || true
      exit 1
    fi
    sleep 1
  done

  if [[ "${ready}" != "1" ]]; then
    echo "[Render MySQL] Recovery server did not become ready." >&2
    cat /tmp/mysql-render-recovery.log >&2 || true
    exit 1
  fi

  mysql --no-defaults --socket="${SOCKET}" -uroot <<SQL
FLUSH PRIVILEGES;
ALTER USER IF EXISTS 'titan_x'@'%' IDENTIFIED BY '${MYSQL_PASSWORD//'/''}';
FLUSH PRIVILEGES;
SQL

  echo "[Render MySQL] titan_x password synchronized successfully."
fi

trap - EXIT
cleanup_recovery
exec /usr/local/bin/docker-entrypoint.sh "$@"
