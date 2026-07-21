import logging
import time
from app.services.email_service import send_email
from Eval.Eval import start_eval

logger = logging.getLogger(__name__)


def format_evaluation_report(results: dict) -> tuple[str, str]:
    """Format evaluation results into standard text and HTML bodies."""
    overall = results.get("overall", {})
    by_domain = results.get("by_domain", {})
    by_difficulty = results.get("by_difficulty", {})

    # Extract dynamic k values from overall keys that start with precision@ or recall@
    k_values = []
    for key in overall.keys():
        if key.startswith("precision@"):
            try:
                k = int(key.split("@")[1])
                if k not in k_values:
                    k_values.append(k)
            except (ValueError, IndexError):
                pass
    k_values.sort()
    if not k_values:
        k_values = [1, 3, 5, 8]  # Fallback

    # Generate text version
    text_lines = []
    text_lines.append("=" * 80)
    text_lines.append("DOCGPT RAG EVALUATION REPORT")
    text_lines.append("=" * 80 + "\n")
    
    text_lines.append("OVERALL METRICS")
    text_lines.append("-" * 40)
    text_lines.append(f"Total Queries: {overall.get('total_queries', 0)}")
    text_lines.append(f"Average Processing Time: {overall.get('avg_processing_time', 0.0):.4f}s")
    text_lines.append(f"Min/Max Processing Time: {overall.get('min_processing_time', 0.0):.4f}s / {overall.get('max_processing_time', 0.0):.4f}s")
    
    text_lines.append("\nPrecision:")
    for k in k_values:
        key = f"precision@{k}"
        if key in overall:
            text_lines.append(f"  @{k}: {overall[key]:.4f}")
            
    text_lines.append("\nRecall:")
    for k in k_values:
        key = f"recall@{k}"
        if key in overall:
            text_lines.append(f"  @{k}: {overall[key]:.4f}")
            
    if by_domain:
        text_lines.append("\nBY DOMAIN")
        text_lines.append("-" * 40)
        for domain, metrics in by_domain.items():
            text_lines.append(f"\n{domain.upper()}:")
            text_lines.append(f"  Precision@5: {metrics.get('precision@5', 0):.4f}")
            text_lines.append(f"  Recall@5: {metrics.get('recall@5', 0):.4f}")
            if "processing_time" in metrics:
                text_lines.append(f"  Avg Processing Time: {metrics.get('processing_time', 0):.4f}s")

    if by_difficulty:
        text_lines.append("\n\nBY DIFFICULTY")
        text_lines.append("-" * 40)
        for difficulty, metrics in by_difficulty.items():
            text_lines.append(f"\n{difficulty.upper()}:")
            text_lines.append(f"  Precision@5: {metrics.get('precision@5', 0):.4f}")
            text_lines.append(f"  Recall@5: {metrics.get('recall@5', 0):.4f}")
            if "processing_time" in metrics:
                text_lines.append(f"  Avg Processing Time: {metrics.get('processing_time', 0):.4f}s")
                
    text_lines.append("\n" + "=" * 80)
    text_report = "\n".join(text_lines)

    # Generate HTML version
    html_lines = []
    html_lines.append("<html>")
    html_lines.append("<head>")
    html_lines.append("<style>")
    html_lines.append("body { font-family: Arial, sans-serif; color: #333; line-height: 1.6; }")
    html_lines.append("h1, h2 { color: #1e3a8a; }")
    html_lines.append("table { border-collapse: collapse; width: 100%; margin-bottom: 20px; }")
    html_lines.append("th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }")
    html_lines.append("th { background-color: #f2f2f2; }")
    html_lines.append(".metric-card { background-color: #f8fafc; border-left: 4px solid #1e3a8a; padding: 15px; margin-bottom: 20px; }")
    html_lines.append("</style>")
    html_lines.append("</head>")
    html_lines.append("<body>")
    html_lines.append("<h1>DocGPT RAG Evaluation Report</h1>")
    
    html_lines.append("<div class='metric-card'>")
    html_lines.append("<h2>Overall Metrics</h2>")
    html_lines.append(f"<p><strong>Total Queries:</strong> {overall.get('total_queries', 0)}</p>")
    html_lines.append(f"<p><strong>Average Processing Time:</strong> {overall.get('avg_processing_time', 0.0):.4f}s</p>")
    html_lines.append(f"<p><strong>Min/Max Processing Time:</strong> {overall.get('min_processing_time', 0.0):.4f}s / {overall.get('max_processing_time', 0.0):.4f}s</p>")
    html_lines.append("</div>")

    # Overall Metrics Table
    html_lines.append("<h2>Precision & Recall</h2>")
    html_lines.append("<table>")
    
    # Generate headers dynamically based on extracted k_values
    header_cols = ["<th>Metric</th>"]
    for k in k_values:
        header_cols.append(f"<th>@{k}</th>")
    html_lines.append(f"<tr>{''.join(header_cols)}</tr>")
    
    html_lines.append("<tr>")
    html_lines.append("<td><strong>Precision</strong></td>")
    for k in k_values:
        html_lines.append(f"<td>{overall.get(f'precision@{k}', 0.0):.4f}</td>")
    html_lines.append("</tr>")
    html_lines.append("<tr>")
    html_lines.append("<td><strong>Recall</strong></td>")
    for k in k_values:
        html_lines.append(f"<td>{overall.get(f'recall@{k}', 0.0):.4f}</td>")
    html_lines.append("</tr>")
    html_lines.append("</table>")

    # By Domain
    if by_domain:
        html_lines.append("<h2>Metrics by Domain</h2>")
        html_lines.append("<table>")
        html_lines.append("<tr><th>Domain</th><th>Precision@5</th><th>Recall@5</th><th>Avg Proc Time</th></tr>")
        for domain, metrics in by_domain.items():
            html_lines.append("<tr>")
            html_lines.append(f"<td>{domain.upper()}</td>")
            html_lines.append(f"<td>{metrics.get('precision@5', 0.0):.4f}</td>")
            html_lines.append(f"<td>{metrics.get('recall@5', 0.0):.4f}</td>")
            avg_time_str = f"{metrics.get('processing_time', 0.0):.4f}s" if 'processing_time' in metrics else 'N/A'
            html_lines.append(f"<td>{avg_time_str}</td>")
            html_lines.append("</tr>")
        html_lines.append("</table>")

    # By Difficulty
    if by_difficulty:
        html_lines.append("<h2>Metrics by Difficulty</h2>")
        html_lines.append("<table>")
        html_lines.append("<tr><th>Difficulty</th><th>Precision@5</th><th>Recall@5</th><th>Avg Proc Time</th></tr>")
        for diff, metrics in by_difficulty.items():
            html_lines.append("<tr>")
            html_lines.append(f"<td>{diff.upper()}</td>")
            html_lines.append(f"<td>{metrics.get('precision@5', 0.0):.4f}</td>")
            html_lines.append(f"<td>{metrics.get('recall@5', 0.0):.4f}</td>")
            avg_time_str = f"{metrics.get('processing_time', 0.0):.4f}s" if 'processing_time' in metrics else 'N/A'
            html_lines.append(f"<td>{avg_time_str}</td>")
            html_lines.append("</tr>")
        html_lines.append("</table>")

    html_lines.append("</body>")
    html_lines.append("</html>")
    html_report = "\n".join(html_lines)

    return text_report, html_report


async def run_eval_and_email_task(ctx: dict, admin_email: str) -> None:
    """Asynchronously runs the evaluation pipeline and emails the generated report to the admin email."""
    logger.info("Starting background evaluation pipeline for admin %s", admin_email)
    try:
        start_time = time.perf_counter()
        results = await start_eval()
        duration = time.perf_counter() - start_time
        
        logger.info("Evaluation pipeline completed in %.2fs. Formatting report...", duration)
        text_report, html_report = format_evaluation_report(results)
        
        subject = f"DocGPT RAG Evaluation Report - {time.strftime('%Y-%m-%d %H:%M:%S')}"
        
        success = send_email(
            to_email=admin_email,
            subject=subject,
            text_content=text_report,
            html_content=html_report,
        )
        
        if success:
            logger.info("Evaluation report successfully sent to %s", admin_email)
        else:
            logger.error("Failed to send evaluation report email to %s", admin_email)
            
    except Exception as e:
        logger.exception("Error during background evaluation task: %s", str(e))
        # Try to send an error email
        try:
            error_msg = f"An error occurred while running the evaluation pipeline:\n\n{str(e)}"
            send_email(
                to_email=admin_email,
                subject="Error in DocGPT Evaluation Pipeline",
                text_content=error_msg,
            )
        except Exception:
            logger.exception("Could not send error report email")
