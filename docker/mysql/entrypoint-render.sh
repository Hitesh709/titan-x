#!/bin/bash
set -euo pipefail

# Render keeps /var/lib/mysql on a persistent disk. The official MySQL image
# only applies MYSQL_* credentials during first initialization, so a later
# Render credential change can leave the application unable to authenticate.
# Before normal startup, repair the application user's password from the
# currently injected MYSQL_PASSWORD without deleting or reinitializing data.

DATADIR="${MYSQL_DATADIR:-/var/lib/mysql}"
SOCKET="/tmp/mysql-render-recovery.sock"
RECOVERY_PID=""

cleanup_recovery() {
  if [[ -n "${RECOVERY_PID}" ]] && kill -0 "${RECOVERY_PID}" 2>/dev/null; then
    mysqladmin --no-defaults --socket="${SOCKET}" -uroot shutdown >/dev/null 2>&1 || true
    kill "${RECOVERY_PID}" >/dev/null 2>&1 || true
    wait "${RECOVERY_PID}" >/dev/null 2>&1 || true
  fi
  rm -f "${SOCKET}" "${SOCKET}-lock"
}

trap cleanup_recovery EXIT

# Only repair an already-initialized data directory. On a brand-new disk the
# official image must perform its normal initialization using MYSQL_*.
if [[ -n "${MYSQL_PASSWORD:-}" && -d "${DATADIR}/mysql" && -f "${DATADIR}/mysql/user.ibd" ]]; then
  echo "[Render MySQL] Existing data directory detected; synchronizing titan_x credentials."

  mysqld \
    --datadir="${DATADIR}" \
    --skip-grant-tables \
    --skip-networking \
    --socket="${SOCKET}" \
    --pid-file=/tmp/mysql-render-recovery.pid \
    >/tmp/mysql-render-recovery.log 2>&1 &
  RECOVERY_PID=$!

  for _ in $(seq 1 60); do
    if mysqladmin --no-defaults --socket="${SOCKET}" ping >/dev/null 2>&1; then
      break
    fi
    if ! kill -0 "${RECOVERY_PID}" 2>/dev/null; then
      echo "[Render MySQL] Recovery server failed to start." >&2
      cat /tmp/mysql-render-recovery.log >&2 || true
      exit 1
    fi
    sleep 1
  done

  mysqladmin --no-defaults --socket="${SOCKET}" ping >/dev/null 2>&1

  mysql --no-defaults --socket="${SOCKET}" -uroot <<SQL
FLUSH PRIVILEGES;
ALTER USER 'titan_x'@'%' IDENTIFIED BY '${MYSQL_PASSWORD//'/''}';
FLUSH PRIVILEGES;
SQL

  echo "[Render MySQL] titan_x password synchronized successfully."
fi

trap - EXIT
cleanup_recovery
exec /usr/local/bin/docker-entrypoint.sh "$@"
