#!/bin/bash
# ============================================================
# 步驟 1：填入你的 GitHub 帳號/倉庫名稱，然後執行此腳本
# 步驟 2：第一次部署成功後，填入 CLOUD_RUN_URL 並再次執行
# ============================================================

GITHUB_REPO="你的帳號/road-running-v1"   # 例如 "roger/road-running-v1"
CLOUD_RUN_URL=""                            # 部署後填入，例如 "https://road-running-bot-xxxx-uc.a.run.app"

PROJECT=road-running-bot
SA=github-actions@road-running-bot.iam.gserviceaccount.com
POOL_NAME=projects/998153550234/locations/global/workloadIdentityPools/github-pool

# ── WIF 綁定（每次只需執行一次）──────────────────────────────
echo "=== 綁定 GitHub 倉庫到服務帳號 ==="
gcloud iam service-accounts add-iam-policy-binding "$SA" \
  --project="$PROJECT" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/${POOL_NAME}/attribute.repository/${GITHUB_REPO}"

# ── Cloud Scheduler（部署後才能執行）────────────────────────
if [[ -n "$CLOUD_RUN_URL" ]]; then
  echo ""
  echo "=== 建立 Cloud Scheduler 推播 job ==="
  gcloud scheduler jobs create http notify-hourly \
    --project="$PROJECT" \
    --location=asia-east1 \
    --schedule="0 * * * *" \
    --time-zone="Asia/Taipei" \
    --uri="${CLOUD_RUN_URL}/notify" \
    --http-method=POST \
    --description="每小時推播台灣時段訂閱使用者" \
    --attempt-deadline=30s
  echo "Cloud Scheduler job 建立完成"
else
  echo ""
  echo "⚠️  CLOUD_RUN_URL 未填入，Cloud Scheduler 略過。"
  echo "    部署完成後，填入 URL 並重新執行此腳本。"
fi

# ── GitHub Secrets 提示 ───────────────────────────────────
echo ""
echo "=== 請將以下值加入 GitHub repository Secrets ==="
echo "(Settings → Secrets and variables → Actions → New repository secret)"
echo ""
printf "%-22s %s\n" "Secret 名稱" "值"
printf "%-22s %s\n" "--------------------" "---------------------------------------------------"
printf "%-22s %s\n" "GCP_PROJECT_ID" "road-running-bot"
printf "%-22s %s\n" "WIF_PROVIDER" "${POOL_NAME}/providers/github-provider"
printf "%-22s %s\n" "WIF_SERVICE_ACCOUNT" "${SA}"
printf "%-22s %s\n" "WEBHOOK_URL" "${CLOUD_RUN_URL:-(部署後填入 Cloud Run URL + /webhook)}"
echo ""
echo "Secrets 設定完成後，push 到 GitHub main branch 即可觸發自動部署。"
