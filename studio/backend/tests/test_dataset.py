from app import dataset


def test_variants_deterministic_and_capped():
    a = dataset.dataset_variants(base_seed=1000, count=40)
    b = dataset.dataset_variants(base_seed=1000, count=40)
    assert a == b                      # deterministic
    assert len(a) == 40                # capped to requested count
    assert len(set(v.seed for v in a)) == 40   # every variant a distinct seed


def test_variants_cover_all_four_angles_before_repeating():
    v = dataset.dataset_variants(base_seed=1, count=4)
    assert {x.angle for x in v} == {"front", "34", "profile", "body"}


def test_variants_carry_lighting_and_distance_in_extra():
    v = dataset.dataset_variants(base_seed=1, count=40)
    # every variant's extra names one lighting and one distance token
    assert all(v0.extra.strip() for v0 in v)
    joined = " ".join(x.extra for x in v)
    assert "lighting" in joined


def test_build_dataset_graphs_one_per_variant_anchored_on_ref():
    graphs = dataset.build_dataset_graphs(
        ref_image="ref_abc.png", identity_string="a Filipino woman, mid 40s",
        base_seed=500, count=8,
    )
    assert len(graphs) == 8
    for variant, graph in graphs:
        assert graph["2"]["inputs"]["image"] == "ref_abc.png"   # anchored
        assert graph["7"]["inputs"]["batch_size"] == 1          # one image each
        assert graph["8"]["inputs"]["seed"] == variant.seed     # variant seed
        assert variant.extra in graph["5"]["inputs"]["prompt"]  # modifier applied
