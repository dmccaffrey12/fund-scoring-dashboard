import { useQuery, useMutation } from "@tanstack/react-query";
import { queryClient } from "@/lib/queryClient";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { useToast } from "@/hooks/use-toast";
import { useState, useRef, useCallback } from "react";
import { Upload, FileSpreadsheet, CheckCircle2, AlertTriangle } from "lucide-react";

export default function CsvUpload() {
  const [dragOver, setDragOver] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState<any>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { toast } = useToast();

  const { data: batches } = useQuery<any[]>({
    queryKey: ["/api/upload/preview"],
  });

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file && file.name.endsWith(".csv")) {
      setSelectedFile(file);
      setResult(null);
    } else {
      toast({ title: "Invalid file", description: "Please upload a CSV file", variant: "destructive" });
    }
  }, [toast]);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      setResult(null);
    }
  };

  const handleUpload = async () => {
    if (!selectedFile) return;

    setUploading(true);
    setProgress(10);

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);

      setProgress(30);

      const API_BASE = "__PORT_5000__".startsWith("__") ? "" : "__PORT_5000__";
      const res = await fetch(`${API_BASE}/api/upload`, {
        method: "POST",
        body: formData,
      });

      setProgress(80);

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.error || "Upload failed");
      }

      const data = await res.json();
      setProgress(100);
      setResult(data);

      // Invalidate all queries
      queryClient.invalidateQueries({ queryKey: ["/api/stats"] });
      queryClient.invalidateQueries({ queryKey: ["/api/funds"] });
      queryClient.invalidateQueries({ queryKey: ["/api/categories"] });
      queryClient.invalidateQueries({ queryKey: ["/api/upload/preview"] });
      queryClient.invalidateQueries({ queryKey: ["/api/monitoring"] });

      toast({ title: "Upload successful", description: `Scored ${data.scoredCount} funds` });
    } catch (err: any) {
      toast({ title: "Upload failed", description: err.message, variant: "destructive" });
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="p-4 lg:p-6 space-y-4 max-w-[1600px]">
      <div>
        <h2 className="text-lg font-bold">CSV Upload</h2>
        <p className="text-xs text-muted-foreground">Upload YCharts fund screener export to score</p>
      </div>

      {/* Drop Zone */}
      <Card
        className={`bg-card border-card-border transition-colors ${dragOver ? "border-primary bg-primary/5" : ""}`}
        onDragOver={e => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
      >
        <CardContent className="p-8">
          <div className="flex flex-col items-center gap-4 text-center">
            <div className={`p-4 rounded-full ${dragOver ? "bg-primary/20" : "bg-muted"}`}>
              <Upload className={`w-8 h-8 ${dragOver ? "text-primary" : "text-muted-foreground"}`} />
            </div>
            <div>
              <p className="text-sm font-medium">
                {selectedFile ? selectedFile.name : "Drag & drop your CSV file here"}
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                {selectedFile
                  ? `${(selectedFile.size / 1024).toFixed(0)} KB`
                  : "YCharts fund screener export (.csv)"}
              </p>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => fileInputRef.current?.click()}
                className="text-xs"
                data-testid="button-browse-file"
              >
                <FileSpreadsheet className="w-3.5 h-3.5 mr-1.5" />
                Browse Files
              </Button>
              {selectedFile && (
                <Button
                  size="sm"
                  onClick={handleUpload}
                  disabled={uploading}
                  className="text-xs gap-1.5"
                  data-testid="button-upload-score"
                >
                  {uploading ? "Scoring..." : "Upload & Score"}
                </Button>
              )}
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              onChange={handleFileSelect}
              className="hidden"
              data-testid="input-file-upload"
            />
          </div>
        </CardContent>
      </Card>

      {/* Progress */}
      {uploading && (
        <Card className="bg-card border-card-border">
          <CardContent className="p-4">
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span>Scoring in progress...</span>
                <span className="font-mono text-xs">{progress}%</span>
              </div>
              <Progress value={progress} className="h-2" />
            </div>
          </CardContent>
        </Card>
      )}

      {/* Result */}
      {result && (
        <Card className="bg-card border-emerald-500/20">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <CheckCircle2 className="w-5 h-5 text-emerald-400" />
              <div>
                <p className="text-sm font-medium">Upload Complete</p>
                <p className="text-xs text-muted-foreground">
                  {result.rowCount.toLocaleString()} rows processed · {result.scoredCount.toLocaleString()} funds scored
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Expected Format */}
      <Card className="bg-card border-card-border">
        <CardHeader className="pb-2 px-4 pt-4">
          <CardTitle className="text-sm font-medium">Expected CSV Format</CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-4">
          <p className="text-xs text-muted-foreground mb-2">
            The CSV should be a YCharts Fund Screener export with these columns:
          </p>
          <div className="bg-muted/30 rounded-md p-3 overflow-x-auto">
            <code className="text-[10px] font-mono text-muted-foreground whitespace-nowrap">
              Symbol, Name, Index Fund, Category Name, Net Expense Ratio, Tracking Error (vs Category) (3Y/5Y/10Y),
              R-Squared (vs Category) (5Y), Share Class Assets Under Management, Downside (vs Category) (5Y/10Y),
              Max Drawdown (5Y/10Y), Information Ratio (vs Category) (3Y/5Y/10Y), Historical Sortino (3Y/5Y/10Y),
              Upside (vs Category) (3Y/5Y/10Y), Total Returns (3Y/5Y/10Y)
            </code>
          </div>
        </CardContent>
      </Card>

      {/* Upload History */}
      {batches && batches.length > 0 && (
        <Card className="bg-card border-card-border">
          <CardHeader className="pb-2 px-4 pt-4">
            <CardTitle className="text-sm font-medium">Upload History</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <table className="w-full">
              <thead className="bg-muted/30">
                <tr>
                  <th className="px-3 py-2 text-left text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">File</th>
                  <th className="px-3 py-2 text-right text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Rows</th>
                  <th className="px-3 py-2 text-right text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Date</th>
                </tr>
              </thead>
              <tbody>
                {batches.map((b: any) => (
                  <tr key={b.id} className="border-t border-border/30">
                    <td className="px-3 py-2 text-sm font-mono">{b.filename}</td>
                    <td className="px-3 py-2 text-sm font-mono tabular-nums text-right">{b.rowCount.toLocaleString()}</td>
                    <td className="px-3 py-2 text-xs text-muted-foreground text-right">
                      {new Date(b.uploadedAt).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
