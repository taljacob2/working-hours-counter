package com.taljacob.workinghours;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;

import androidx.activity.result.ActivityResult;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.ActivityCallback;
import com.getcapacitor.annotation.CapacitorPlugin;

import java.io.OutputStream;

@CapacitorPlugin(name = "FileSaver")
public class FileSaverPlugin extends Plugin {

    @PluginMethod
    public void saveFile(PluginCall call) {
        String filename = call.getString("filename", "export.csv");
        String mimeType = call.getString("mimeType", "*/*");

        Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType(mimeType);
        intent.putExtra(Intent.EXTRA_TITLE, filename);

        startActivityForResult(call, intent, "saveFileResult");
    }

    @ActivityCallback
    private void saveFileResult(PluginCall call, ActivityResult result) {
        if (call == null) return;
        if (result.getResultCode() != Activity.RESULT_OK) {
            call.reject("cancelled");
            return;
        }
        Intent data = result.getData();
        if (data == null || data.getData() == null) {
            call.reject("No URI returned");
            return;
        }
        Uri uri = data.getData();
        String content = call.getString("content", "");
        boolean isBase64 = call.getBoolean("isBase64", false);
        try {
            byte[] bytes = isBase64
                ? android.util.Base64.decode(content, android.util.Base64.DEFAULT)
                : content.getBytes("UTF-8");
            OutputStream out = getContext().getContentResolver().openOutputStream(uri);
            out.write(bytes);
            out.close();
            call.resolve();
        } catch (Exception e) {
            call.reject("Write failed: " + e.getMessage());
        }
    }
}
