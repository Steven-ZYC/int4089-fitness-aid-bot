#include <cstdio>
#include <memory>
#include "esp_camera.h"
#include "esp_chip_info.h"
#include "esp_flash.h"
#include "esp_heap_caps.h"
#include "esp_psram.h"
#include "esp_private/esp_clk.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sdkconfig.h"
#if CONFIG_BENCH_POSE
#include "dl_image_preprocessor.hpp"
#include "dl_model_base.hpp"
#include "dl_pose_yolo11_postprocessor.hpp"
#include "model_meta.h"
extern const uint8_t model_start[] asm("_binary_yolo11n_pose_espdl_start");
#endif

static void error(const char *reason)
{
    printf("BENCH_ERROR {\"reason\":\"%s\"}\n", reason);
    fflush(stdout);
}

static esp_err_t init_camera()
{
    // Same AI Thinker pin map as Yuankun's working USB capture sketch.
    camera_config_t c = {};
    c.pin_pwdn = 32; c.pin_reset = -1; c.pin_xclk = 0;
    c.pin_sccb_sda = 26; c.pin_sccb_scl = 27;
    c.pin_d0 = 5; c.pin_d1 = 18; c.pin_d2 = 19; c.pin_d3 = 21;
    c.pin_d4 = 36; c.pin_d5 = 39; c.pin_d6 = 34; c.pin_d7 = 35;
    c.pin_vsync = 25; c.pin_href = 23; c.pin_pclk = 22;
    c.ledc_timer = LEDC_TIMER_0; c.ledc_channel = LEDC_CHANNEL_0;
    c.xclk_freq_hz = 20000000;
    c.pixel_format = PIXFORMAT_RGB565;
    c.frame_size = FRAMESIZE_QQVGA; // 160x120; model letterboxes to its own input size.
    c.fb_count = 1;
    c.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
    c.fb_location = esp_psram_is_initialized() ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;
    return esp_camera_init(&c);
}

extern "C" void app_main()
{
    setvbuf(stdout, nullptr, _IOLBF, 0);
    esp_chip_info_t chip;
    esp_chip_info(&chip);
    uint32_t flash_bytes = 0;
    if (esp_flash_get_size(nullptr, &flash_bytes) != ESP_OK) {
        error("cannot_read_flash_size"); return;
    }
    const size_t psram_bytes = esp_psram_is_initialized() ? esp_psram_get_size() : 0;
#if CONFIG_BENCH_POSE
    constexpr const char *mode = "pose";
    constexpr const char *model_sha = BENCH_MODEL_SHA;
    constexpr int input_size = BENCH_MODEL_SIZE;
#else
    constexpr const char *mode = "camera_only";
    constexpr const char *model_sha = "none";
    constexpr int input_size = 0;
#endif
    printf("BENCH_INFO {\"mode\":\"%s\",\"chip\":\"esp32\",\"revision\":%d,"
           "\"cores\":%d,\"cpu_mhz\":%d,\"flash_bytes\":%lu,\"psram_bytes\":%u,"
           "\"mapped_psram_bytes\":%u,\"input_size\":%d,\"model_sha256\":\"%s\","
           "\"idf\":\"%s\",\"runtime\":\"auto\"}\n",
           mode, chip.revision, chip.cores, esp_clk_cpu_freq() / 1000000,
           static_cast<unsigned long>(flash_bytes), static_cast<unsigned>(psram_bytes),
           static_cast<unsigned>(heap_caps_get_total_size(MALLOC_CAP_SPIRAM)),
           input_size, model_sha, esp_get_idf_version());
#if CONFIG_BENCH_POSE
    if (!psram_bytes) { error("psram_not_initialized_no_pose_benchmark"); return; }
    // Keep weights in flash to save PSRAM. This may be slower than copying weights to PSRAM.
    auto model = std::make_unique<dl::Model>(reinterpret_cast<const char *>(model_start),
        fbs::MODEL_LOCATION_IN_FLASH_RODATA, 0, dl::MEMORY_MANAGER_GREEDY, nullptr, false);
    model->minimize();
    auto *input = model->get_input();
    if (!input || !input->data || input->shape != std::vector<int>({1, input_size, input_size, 3}) ||
        input->dtype != dl::DATA_TYPE_INT8) {
        error("model_input_must_be_int8_nhwc_matching_manifest"); return;
    }
    for (const char *name : {"box0", "score0", "box1", "score1", "box2", "score2", "kpt0", "kpt1", "kpt2"}) {
        auto *out = model->get_output(name);
        if (!out || !out->data) { error("invalid_pose_head_outputs"); return; }
    }
    dl::image::ImagePreprocessor pre(model.get(), {0, 0, 0}, {255, 255, 255});
    pre.enable_letterbox({114, 114, 114});
    dl::detect::yolo11posePostProcessor post(model.get(), &pre, 0.25f, 0.7f, 1,
        {{8, 8, 4, 4}, {16, 16, 8, 8}, {32, 32, 16, 16}});
#endif
    if (init_camera() != ESP_OK) { error("camera_init_failed"); return; }
    auto *sensor = esp_camera_sensor_get();
    printf("BENCH_SENSOR {\"pid\":%u,\"width\":160,\"height\":120,\"format\":\"RGB565BE\"}\n",
           sensor ? sensor->id.PID : 0);
    // Allow a host monitor to attach. Does not count toward measured FPS.
    vTaskDelay(pdMS_TO_TICKS(2000));
    for (int i = -CONFIG_BENCH_WARMUP; i < CONFIG_BENCH_SAMPLES; ++i) {
        const int64_t start = esp_timer_get_time();
        camera_fb_t *fb = esp_camera_fb_get();
        const int64_t captured = esp_timer_get_time();
        if (!fb) { error("camera_capture_failed"); break; }
        int64_t pre_us = 0, infer_us = 0, post_us = 0;
        size_t poses = 0;
#if CONFIG_BENCH_POSE
        dl::image::img_t img = {.data=fb->buf, .width=static_cast<uint16_t>(fb->width),
            .height=static_cast<uint16_t>(fb->height), .pix_type=dl::image::DL_IMAGE_PIX_TYPE_RGB565BE};
        pre.preprocess(img);
        const int64_t prepared = esp_timer_get_time();
        model->run(dl::RUNTIME_MODE_AUTO);
        const int64_t inferred = esp_timer_get_time();
        post.clear_result();
        post.postprocess();
        poses = post.get_result(img.width, img.height).size();
        const int64_t processed = esp_timer_get_time();
        pre_us = prepared - captured;
        infer_us = inferred - prepared;
        post_us = processed - inferred;
#endif
        esp_camera_fb_return(fb);
        const int64_t end = esp_timer_get_time();
        if (i >= 0) {
            printf("BENCH_ROW {\"mode\":\"%s\",\"frame\":%d,\"start_us\":%lld,\"end_us\":%lld,"
                   "\"capture_us\":%lld,\"pre_us\":%lld,\"infer_us\":%lld,\"post_us\":%lld,"
                   "\"poses\":%u,\"free_psram_bytes\":%u}\n",
                   mode, i, start, end, captured-start, pre_us, infer_us, post_us,
                   static_cast<unsigned>(poses), static_cast<unsigned>(heap_caps_get_free_size(MALLOC_CAP_SPIRAM)));
        }
        vTaskDelay(1);
    }
    esp_camera_deinit();
    puts("BENCH_DONE");
}
