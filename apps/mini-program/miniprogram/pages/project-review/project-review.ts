import { api } from "../../services/api";
import { runtimeConfig } from "../../config";
import { visiblePage } from "../../services/pagination.js";
import type { ProductSpec, ProjectMember, ProjectReview } from "../../types";

type ReviewTab = "specs" | "members" | "raci";

interface TabTapEvent {
  currentTarget: { dataset: { tab: ReviewTab } };
}

interface SpecView extends ProductSpec {
  detail: string;
}

interface RaciView {
  code: string;
  name: string;
  output: string;
  roles: Array<{ key: "R" | "A" | "C" | "I"; names: string }>;
}

const valueOrEmpty = (value: string | null) => value?.trim() || "";

Page({
  data: {
    projectId: "",
    review: null as ProjectReview | null,
    specs: [] as SpecView[],
    visibleSpecs: [] as SpecView[],
    members: [] as ProjectMember[],
    raciRows: [] as RaciView[],
    visibleRaciRows: [] as RaciView[],
    specPage: 1,
    raciPage: 1,
    activeTab: "specs" as ReviewTab,
    loading: true,
  },
  async onLoad(options: Record<string, string | undefined>) {
    const projectId = options.projectId || wx.getStorageSync<string>("current_project_id");
    this.setData({ projectId });
    try {
      const review = await api.projectReview(projectId);
      const specs = review.product_specs.map((spec) => ({
        ...spec,
        detail: [spec.configuration, spec.core_information, spec.selected_model]
          .map(valueOrEmpty)
          .filter(Boolean)
          .join(" · ") || "—",
      }));
      const raciRows = review.milestones.map((milestone) => ({
        code: milestone.code,
        name: milestone.name,
        output: milestone.output || "—",
        roles: (["R", "A", "C", "I"] as const).map((key) => ({
          key,
          names: milestone.assignments[key]?.join("、") || "—",
        })),
      }));
      this.setData({
        review,
        specs,
        visibleSpecs: visiblePage(specs, 1, runtimeConfig.projectReviewPageSize),
        members: review.members,
        raciRows,
        visibleRaciRows: visiblePage(raciRows, 1, runtimeConfig.projectReviewPageSize),
        specPage: 1,
        raciPage: 1,
      });
    } catch (error) {
      wx.showToast({ title: (error as Error).message || "项目资料加载失败", icon: "none" });
    } finally {
      this.setData({ loading: false });
    }
  },
  selectTab(event: TabTapEvent) {
    this.setData({ activeTab: event.currentTarget.dataset.tab });
  },
  showMoreSpecs() {
    const specPage = this.data.specPage + 1;
    this.setData({
      specPage,
      visibleSpecs: visiblePage(
        this.data.specs,
        specPage,
        runtimeConfig.projectReviewPageSize,
      ),
    });
  },
  showMoreRaci() {
    const raciPage = this.data.raciPage + 1;
    this.setData({
      raciPage,
      visibleRaciRows: visiblePage(
        this.data.raciRows,
        raciPage,
        runtimeConfig.projectReviewPageSize,
      ),
    });
  },
});
